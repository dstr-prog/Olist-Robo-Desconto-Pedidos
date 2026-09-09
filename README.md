# Robô Olist — Desconto em Pedidos de Venda

Aplica um desconto **percentual** em cada pedido visível na tela, um a um (o Olist não tem ação em lote para isso).

Fluxo por pedido: clicar na linha → **editar** → preencher **Desconto** com sufixo `%` → **salvar** → **voltar**.

## Instalação (uma vez)

No PowerShell:

```powershell
cd C:\dstr-prog\olist\robo-desconto-ped
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

> O robô **não** abre um Chromium próprio: ele se conecta no **Chrome já aberto** (porta 9222).

## Como usar

O Chrome **já pode estar aberto** pelo `iniciar_chrome_olist.bat` do robô de exclusão de pedidos. Nesse caso, deixe a aba **Pedidos de venda** filtrada e pule para o passo 4.

1. **Feche todo o Chrome** (senão a porta de depuração não sobe) — só se ainda não estiver aberto com a porta 9222.
2. Rode `iniciar_chrome_olist.bat`
   - Abre o Chrome com depuração na porta `9222`
   - Reutiliza o perfil de `..\robo-exclusao` se existir (mesmo login)
3. Na aba **Pedidos de venda**, aplique o filtro e deixe a lista pronta.
4. Dê duplo clique em **`executar_robo.bat`**.

   O lançador testa a conexão e a grid, pede o **percentual** (ex.: `10` ou `10,5`) e só inicia após a confirmação `S`.

5. Para **parar**: `Ctrl+C` na janela do terminal.

### Alternativa no PowerShell

```powershell
cd C:\dstr-prog\olist\robo-desconto-ped
.\.venv\Scripts\python.exe desconto_pedidos_olist.py --percentual 10
```

Simulação (abre cada pedido, registra o que faria e volta **sem salvar**):

```powershell
.\.venv\Scripts\python.exe desconto_pedidos_olist.py --percentual 10 --simular
```

## Regras

- Processa **somente os pedidos visíveis** na grid atual.
- Se o campo **Desconto** já tiver valor (diferente de zero), o pedido é ignorado.
- O **Total da venda** não fica abaixo de **R$ 10,00**. Se o percentual informado derrubaria o total, ele é reduzido só naquele pedido.
- Pedidos que já estão em R$ 10,00 (ou menos) também são ignorados.

## Log

Cada execução grava um TXT em:

`C:\dstr-prog\olist\robo-desconto-ped\logs\desconto_YYYYMMDD_HHMMSS.txt`

## Observações

- O percentual é pedido no início (`executar_robo.bat`) para não misturar com a tela do Olist.
- Se algum seletor falhar (UI do Olist mudou), rode de novo e envie o trecho do log com o erro — ajustamos os localizadores.
