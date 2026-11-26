"""Papo social (oi, obrigado, tchau): responde na hora, sem busca no FAQ e sem gastar o modelo."""
import re
import unicodedata

_SAUDACAO = {"oi", "ola", "oie", "opa", "eai", "e ai", "bom dia", "boa tarde", "boa noite", "ola tudo bem", "oi tudo bem", "tudo bem", "oi lumi", "ola lumi"}
_AGRADECIMENTO = {"obrigado", "obrigada", "obg", "brigado", "valeu", "muito obrigado", "muito obrigada", "obrigado lumi", "obrigada lumi", "valeu lumi", "show obrigado", "perfeito obrigado", "perfeito obrigada"}
_DESPEDIDA = {"tchau", "ate logo", "ate mais", "ate a proxima", "falou", "flw", "tchau lumi"}

RESPOSTAS = {
    "saudacao": "Oi! Eu sou a Lumi. Posso explicar como usar o sistema, consultar seus números ou abrir um cadastro para você. O que você precisa?",
    "agradecimento": "Por nada! Se surgir outra dúvida, é só chamar.",
    "despedida": "Até mais! Quando precisar, estou por aqui.",
}


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", sem_acento)).strip()


def resposta_de_conversa(pergunta: str) -> str | None:
    """Só quando a mensagem INTEIRA é papo social. "oi, como crio um orçamento?" segue para a busca normal."""
    t = _normalizar(pergunta)
    if t in _SAUDACAO:
        return RESPOSTAS["saudacao"]
    if t in _AGRADECIMENTO:
        return RESPOSTAS["agradecimento"]
    if t in _DESPEDIDA:
        return RESPOSTAS["despedida"]
    return None
