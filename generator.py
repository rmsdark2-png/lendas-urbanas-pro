import os
import json
import subprocess
import sys
import time
import requests
from gtts import gTTS

os.makedirs("output", exist_ok=True)
os.makedirs("temp", exist_ok=True)

lenda_id = sys.argv[1] if len(sys.argv) > 1 else "1"

with open("lendas.json", "r", encoding="utf-8") as f:
    dados = json.load(f)

if lenda_id not in dados:
    print(f"Erro: Lenda ID {lenda_id} não encontrada no lendas.json")
    sys.exit(1)

lenda = dados[lenda_id]
titulo = lenda["titulo"]
cenas = lenda["cenas"]

print(f"Iniciando a geração da lenda: {titulo} (ID: {lenda_id})")

# 1. Gerar narração unificada e normalização de áudio
texto_completo = " ".join([cena["narracao"] for cena in cenas])
tts = gTTS(text=texto_completo, lang="pt", slow=False)
tts.save("temp/narracao_bruta.mp3")

subprocess.run([
    "ffmpeg", "-y", "-i", "temp/narracao_bruta.mp3",
    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,volume=0.0dB",
    "temp/narracao.mp3"
], check=True)

# 2. Processar cada cena descarregando a imagem temática correspondente
clips_list = []
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

for i, cena in enumerate(cenas):
    prompt_base = cena["prompt_ia"]
    cena_id = cena["id"]
    legenda_texto = cena["legenda"]
    
    prompt_completo = f"{prompt_base}, dark cinematic horror, moody lighting, high quality"
    img_url = f"https://image.pollinations.ai/prompt/{prompt_completo.replace(' ', '%20')}?width=720&height=1280&nologo=true&seed={cena_id*77}"
    
    img_path = f"temp/cena_{cena_id}.jpg"
    sucesso = False
    
    for tentativa in range(3):
        try:
            response = requests.get(img_url, timeout=25)
            if response.status_code == 200 and response.content is not None and len(response.content) > 5000:
                with open(img_path, "wb") as handler:
                    handler.write(response.content)
                if os.path.exists(img_path) and os.path.getsize(img_path) > 5000:
                    sucesso = True
                    break
        except Exception as e:
            print(f"Tentativa {tentativa+1} falhou: {e}")
        time.sleep(3)
        
    # Fallback de segurança se falhar a rede
    if not sucesso:
        print(f"Aviso: Usando fundo de segurança para a cena {cena_id}")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", 
            "color=c=black:s=720x1280:d=1", 
            "-frames:v", "1", img_path
        ], check=True)

    # 3. Gerar clipe com efeito Ken Burns e legendas profissionais
    clip_path = f"temp/cena_{cena_id}.mp4"
    legenda_limpa = legenda_texto.replace("'", "").replace('"', "").replace(":", "\\:")
    
    filtro_video = (
        "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
        "zoompan=z='min(zoom+0.0012,1.12)':d=200:s=720x1280,"
        f"drawtext=fontfile='{font_path}':text='{legenda_limpa}':fontcolor=white:fontsize=40:borderw=4:bordercolor=black:"
        "x=(w-text_w)/2:y=h-220"
    )
    
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", img_path,
        "-t", "5.71",
        "-vf", filtro_video,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        clip_path
    ], check=True)
    
    clips_list.append(clip_path)

# Juntar todos os clipes numa lista para o FFmpeg
with open("temp/concat_list.txt", "w", encoding="utf-8") as f:
    for clip in clips_list:
        f.write(f"file '{os.path.abspath(clip)}'\n")

subprocess.run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", "temp/concat_list.txt",
    "-c", "copy", "temp/video_base.mp4"
], check=True)

# 4. Mistura final de áudio e vídeo
output_file = f"output/lenda_{lenda_id}_{titulo.replace(' ', '_')}.mp4"
subprocess.run([
    "ffmpeg", "-y",
    "-i", "temp/video_base.mp4",
    "-i", "temp/narracao.mp3",
    "-filter_complex", "[1:a]volume=0.0dB[audio]",
    "-map", "0:v", "-map", "[audio]",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
    output_file
], check=True)

print(f"Vídeo gerado com sucesso: {output_file}")
