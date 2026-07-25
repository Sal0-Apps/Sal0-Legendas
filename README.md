# 🎬 Sal0 Legendas - Legendador & Tradutor Automático de Vídeos (v1.0.0)

O **Sal0 Legendas** é um aplicativo self-hosted profissional projetado para a **legendagem automática e tradução de vídeos de qualquer duração**, utilizando o **Whisper AI**, detecção de voz por **Silero VAD** e motores de tradução neural (com padrão automático para **Português do Brasil - pt-BR**).

---

## 🌟 Principais Recursos

1. **Sem Limite de Duração de Vídeo**: Suporta arquivos curtos ou vídeos longos (1h, 2h, palestras, filmes) sem travamentos ou estouro de memória.
2. **Qualidade Original Preservada**: Os vídeos finais com legenda embutida mantêm 100% da resolução, framerate e qualidade de imagem do vídeo original.
3. **Tradução Automática Configurável (Padrão: pt-BR)**: Traduz automaticamente o áudio detectado (inglês, espanhol, japonês, etc.) para Português do Brasil ou mais de 30 idiomas.
4. **Formatos Flexíveis de Exportação**:
   - **Legendas Separadas**: Baixe arquivos `.SRT`, `.VTT`, `.ASS` ou `.TXT`.
   - **Vídeo MP4 com Legenda Embutida**: Hardsub de alta definição com estilização personalizada (posição, tamanho, cor, caixa de fundo).
5. **Revisão Intermediária (Pausa 75%)**: Editor interativo em tempo real para ajustar textos e marcações de tempo em `MM:SS.ms`.
6. **Integração com o Bot do Telegram**: Receba alertas e vídeos legendados diretamente no celular com links de acesso local e remoto.

---

## 🚀 Como Executar com Docker Compose

```bash
docker compose up -d --build
```

Acesse a interface no seu navegador em: `http://localhost:8001`
