"""Medicao de audiencia por fonte (F5)."""
from app.engine.metrics import is_bot


def test_is_bot_reconhece_robos():
    """Sem esse filtro, o relatorio de parceria contaria o Googlebot como
    interesse de comprador no lote do leiloeiro."""
    assert is_bot("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
    assert is_bot("ClaudeBot/1.0")
    assert is_bot("python-requests/2.31.0")
    assert is_bot("curl/8.4.0")
    assert is_bot("facebookexternalhit/1.1")
    assert is_bot("Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120")


def test_is_bot_deixa_passar_navegador():
    assert not is_bot(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    assert not is_bot(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    )


def test_is_bot_sem_user_agent():
    """Cliente sem UA e robo mal-educado, nao visitante: nao conta audiencia."""
    assert is_bot(None)
    assert is_bot("")
    assert is_bot("curl")
