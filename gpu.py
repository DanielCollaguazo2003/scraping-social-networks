import torch
from transformers import pipeline

def verificar_uso_gpu():
    print("🧠 Verificando si hay GPU disponible para PyTorch...")
    if torch.cuda.is_available():
        print(f"✅ GPU detectada: {torch.cuda.get_device_name(0)}")
    else:
        print("❌ No se detectó GPU. Usando CPU.")
        return

    print("\n🚀 Cargando modelo en GPU...")
    pipe = pipeline("sentiment-analysis", device=0)  # 0 = GPU, -1 = CPU

    texto = "Me encanta este lugar, la comida es espectacular y el servicio muy amable."
    resultado = pipe(texto)

    print("\n📊 Resultado del análisis:")
    print(resultado)

verificar_uso_gpu()
