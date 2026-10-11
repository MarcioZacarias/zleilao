Escrito para: equipe técnica / TI do Freitas Leiloeiro (não é texto para o Márcio).

---

**Assunto: cadeia de certificado incompleta em www.freitasleiloeiro.com.br**

Olá,

Identificamos um problema de configuração TLS no servidor de vocês que quebra
integrações automatizadas. Navegadores não mostram erro, então é provável que
tenha passado despercebido.

**O que acontece**

O servidor apresenta um certificado intermediário que não corresponde ao
certificado do site — e que, além disso, está expirado:

- Certificado do site: `CN=*.freitasleiloeiro.com.br`
  emitido por **GlobalSign GCC R6 AlphaSSL CA 2025**
- Intermediário enviado pelo servidor: **AlphaSSL CA - SHA256 - G2**,
  expirado em **20/02/2024**

Como o intermediário correto não é enviado, a cadeia não fecha. A verificação
falha com:

```
verify error:num=21: unable to verify the first certificate
Verify return code: 21
```

Navegadores contornam isso sozinhos, buscando o intermediário pela extensão
AIA do certificado. Clientes mais estritos — bibliotecas HTTP, integrações,
monitoramento e plataformas de borda — não fazem essa busca e simplesmente
não conseguem conectar.

Para reproduzir:

```
openssl s_client -connect www.freitasleiloeiro.com.br:443 \
                 -servername www.freitasleiloeiro.com.br
```

O mesmo ocorre em `app.`, `api.` e `portal.freitasleiloeiro.com.br`.

**Como corrigir**

O intermediário correto está publicado pela própria GlobalSign, no endereço
que o certificado de vocês indica:

```
http://secure.globalsign.com/cacert/gsgccr6alphasslca2025.crt
```

Basta substituir o intermediário atual por esse no arquivo de cadeia do
servidor (`ssl_certificate` no nginx, `SSLCertificateChainFile` no Apache) e
recarregar o serviço. Não é preciso reemitir o certificado do site, que está
válido até 25/10/2026.

Depois da correção, o comando acima deve terminar com `Verify return code: 0`.

Qualquer dúvida, ficamos à disposição.
