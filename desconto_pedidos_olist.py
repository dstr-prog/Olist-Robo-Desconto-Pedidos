"""
Robo Olist - desconto percentual em Pedidos de Venda (um a um).

Pre-requisitos:
  1. Chrome ja aberto com depuracao na porta 9222
     (iniciar_chrome_olist.bat desta pasta, ou o bat de exclusao de pedidos).
  2. Login feito e tela Pedidos de venda aberta, com o filtro/grid prontos.
  3. executar_robo.bat  (pede o percentual)  OU
     python desconto_pedidos_olist.py --percentual 10

Interromper: Ctrl+C
"""

from __future__ import annotations

import argparse
import logging
import math
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

# --- Configuracao -----------------------------------------------------------

CDP_URL = "http://127.0.0.1:9222"
URL_PEDIDOS = "erp.olist.com/vendas"
TOTAL_MINIMO_PADRAO = 10.00
NATUREZA_SEM_DESCONTO = "venda de mercadorias de terceiros para contribuinte"

TIMEOUT_ACAO_MS = 30_000
TIMEOUT_SALVAR_MS = 120_000
DELAY_ENTRE_CLIQUES_S = 0.6
DELAY_APOS_VOLTAR_S = 1.2
DELAY_APOS_PAGINACAO_S = 1.5
DELAY_APOS_CALCULO_S = 0.8
MAX_ERROS_SEGUIDOS = 3

DIR_BASE = Path(__file__).resolve().parent
DIR_LOGS = DIR_BASE / "logs"
DIR_LOGS.mkdir(exist_ok=True)
ARQUIVO_LOG = DIR_LOGS / f"desconto_{datetime.now():%Y%m%d_%H%M%S}.txt"

# ---------------------------------------------------------------------------


def setup_log() -> logging.Logger:
    logger = logging.getLogger("olist_desconto")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(ARQUIVO_LOG, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


log = setup_log()


def parse_numero_br(texto: str | None) -> float:
    if texto is None:
        return 0.0
    raw = str(texto).strip()
    raw = raw.replace("R$", "").replace("%", "").strip()
    if not raw:
        return 0.0
    raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def formatar_percentual(valor: float) -> str:
    texto = f"{valor:.2f}".replace(".", ",")
    return f"{texto}%"


def parse_percentual(texto: str) -> float:
    bruto = (texto or "").strip().replace("%", "").strip()
    if not bruto:
        raise ValueError("Percentual vazio.")
    valor = parse_numero_br(bruto)
    if valor <= 0 or valor >= 100:
        raise ValueError("O percentual deve ser maior que 0 e menor que 100.")
    return valor


def normalizar_texto(texto: str | None) -> str:
    s = unicodedata.normalize("NFD", texto or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def natureza_bloqueia_desconto(texto: str | None) -> bool:
    return normalizar_texto(texto) == NATUREZA_SEM_DESCONTO


def desconto_eh_percentual(*textos: str | None) -> bool:
    return any("%" in str(texto or "") for texto in textos)


def encontrar_pagina_pedidos(browser) -> Page:
    candidatos: list[Page] = []
    for ctx in browser.contexts:
        for page in ctx.pages:
            url = (page.url or "").lower()
            if URL_PEDIDOS in url:
                candidatos.append(page)

    if not candidatos:
        raise RuntimeError(
            "Nenhuma aba de Pedidos de venda encontrada.\n"
            "Deixe aberta a tela filtrada em https://erp.olist.com/vendas#list "
            f"e confirme que o Chrome esta com depuracao em {CDP_URL}."
        )

    page = candidatos[-1]
    page.bring_to_front()
    log.info("Aba encontrada: %s", page.url)
    return page


def esperar_sem_aguarde(page: Page, timeout_ms: int = TIMEOUT_ACAO_MS) -> None:
    try:
        page.wait_for_function(
            "() => !document.body.classList.contains('wait-block-open')",
            timeout=timeout_ms,
        )
    except PlaywrightTimeout:
        log.warning("Overlay de espera ainda visivel apos %sms.", timeout_ms)


def listar_pedidos_visiveis(page: Page) -> list[dict]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('table.thumb-table tbody tr[idvenda]')).map(tr => ({
            id: String(tr.getAttribute('idvenda') || tr.id || ''),
            numero: String(tr.getAttribute('numeropedido') || ''),
            valor: String(tr.getAttribute('valor') || ''),
            situacao: String(tr.getAttribute('nomesituacao') || ''),
            podeEditar: String(tr.getAttribute('podeeditar') || ''),
            cliente: ((tr.querySelector('td.tline.footable-visible:nth-of-type(8)') || {}).innerText || '').trim()
        }))"""
    )


def ler_info_paginacao(page: Page) -> dict:
    return page.evaluate(
        """() => {
            const pag = document.querySelector('ul.pagination.hidden-xs')
                || document.querySelector('ul.pagination');
            if (!pag) {
                return { paginaAtual: 1, totalPaginas: 1, temProxima: false, linhas: 0 };
            }

            const active = pag.querySelector('li.active a.link-pg');
            const paginaAtual = active
                ? parseInt(active.getAttribute('data-pagina') || '1', 10)
                : 1;
            const numeros = Array.from(pag.querySelectorAll('a.link-pg[data-pagina]'))
                .map((a) => parseInt(a.getAttribute('data-pagina') || '0', 10))
                .filter((n) => n > 0);
            const totalPaginas = numeros.length ? Math.max(...numeros) : paginaAtual;
            const pnext = pag.querySelector('li.pnext');
            const temProxima = !!(pnext && !pnext.classList.contains('disabled'));
            const linhas = document.querySelectorAll('table.thumb-table tbody tr[idvenda]').length;

            return { paginaAtual, totalPaginas, temProxima, linhas };
        }"""
    )


def aguardar_mudanca_pagina(page: Page, pagina_anterior: int, id_antes: str | None) -> None:
    page.wait_for_function(
        """(args) => {
            if (document.body.classList.contains('wait-block-open')) return false;
            const pag = document.querySelector('ul.pagination.hidden-xs')
                || document.querySelector('ul.pagination');
            const active = pag && pag.querySelector('li.active a.link-pg');
            const paginaAtual = active
                ? parseInt(active.getAttribute('data-pagina') || '0', 10)
                : 0;
            if (paginaAtual > args.paginaAnterior) return true;
            const idAtual = (document.querySelector('table.thumb-table tbody tr[idvenda]') || {})
                .getAttribute('idvenda');
            return !!(idAtual && args.idAntes && idAtual !== args.idAntes);
        }""",
        arg={"paginaAnterior": pagina_anterior, "idAntes": id_antes or ""},
        timeout=TIMEOUT_ACAO_MS,
    )
    esperar_sem_aguarde(page)
    time.sleep(DELAY_APOS_PAGINACAO_S)


def ir_para_proxima_pagina(page: Page) -> bool:
    if not na_lista(page):
        voltar_para_lista(page)

    info = ler_info_paginacao(page)
    pagina_atual = int(info.get("paginaAtual") or 1)
    if not info.get("temProxima"):
        return False

    id_antes = page.evaluate(
        """() => {
            const tr = document.querySelector('table.thumb-table tbody tr[idvenda]');
            return tr ? String(tr.getAttribute('idvenda') || tr.id || '') : '';
        }"""
    )

    proxima = pagina_atual + 1
    btn = page.locator("ul.pagination.hidden-xs li.pnext a.link-pg").first
    if btn.count() == 0:
        btn = page.locator(f'ul.pagination.hidden-xs a.link-pg[data-pagina="{proxima}"]').first
    if btn.count() == 0:
        btn = page.locator(f'ul.pagination a.link-pg[data-pagina="{proxima}"]').first
    if btn.count() == 0:
        log.warning("Botao da pagina %s nao encontrado.", proxima)
        return False

    log.info("Indo para a pagina %s...", proxima)
    btn.click(force=True, timeout=TIMEOUT_ACAO_MS)
    aguardar_mudanca_pagina(page, pagina_atual, id_antes)

    info_depois = ler_info_paginacao(page)
    log.info(
        "Pagina atual: %s/%s | linhas=%s",
        info_depois.get("paginaAtual"),
        info_depois.get("totalPaginas"),
        info_depois.get("linhas"),
    )
    return int(info_depois.get("paginaAtual") or 0) > pagina_atual


def na_lista(page: Page) -> bool:
    url = (page.url or "").lower()
    return "#list" in url or url.rstrip("/").endswith("/vendas")


def na_detalhe(page: Page, id_venda: str | None = None) -> bool:
    hash_atual = ""
    try:
        hash_atual = page.evaluate("() => location.hash || ''") or ""
    except Exception:
        hash_atual = page.url or ""
    if id_venda:
        return f"edit/{id_venda}" in hash_atual
    return "#edit/" in hash_atual


def voltar_para_lista(page: Page) -> None:
    if na_lista(page):
        esperar_sem_aguarde(page)
        return

    btn = page.locator("a.btn-breadcrumb-voltar").first
    if btn.count() == 0:
        page.evaluate("() => { if (typeof cancelarVenda === 'function') cancelarVenda(); }")
    else:
        btn.click(timeout=TIMEOUT_ACAO_MS)

    try:
        page.wait_for_function(
            "() => (location.hash || '').indexOf('list') >= 0",
            timeout=TIMEOUT_ACAO_MS,
        )
    except PlaywrightTimeout:
        log.warning("Hash nao voltou para #list; tentando history list.")
        page.evaluate("() => { if (window.jQuery && jQuery.history) jQuery.history.add('list'); }")

    esperar_sem_aguarde(page)
    time.sleep(DELAY_APOS_VOLTAR_S)


def abrir_pedido(page: Page, pedido: dict) -> None:
    id_venda = pedido["id"]
    if na_detalhe(page, id_venda):
        esperar_sem_aguarde(page)
        return

    if not na_lista(page):
        voltar_para_lista(page)

    linha = page.locator(f'table.thumb-table tbody tr[idvenda="{id_venda}"]').first
    if linha.count() == 0:
        log.info("Linha %s nao visivel; abrindo via editarVenda().", id_venda)
        page.evaluate("(id) => { if (typeof editarVenda === 'function') editarVenda(id, true); }", id_venda)
    else:
        alvo = linha.locator("td.tline.footable-visible").first
        alvo.click(timeout=TIMEOUT_ACAO_MS)

    page.wait_for_function(
        """(id) => {
            const hash = location.hash || '';
            const campo = document.getElementById('id');
            return hash.indexOf('edit/' + id) >= 0 && campo && String(campo.value) === String(id);
        }""",
        arg=id_venda,
        timeout=TIMEOUT_ACAO_MS,
    )
    esperar_sem_aguarde(page)
    time.sleep(DELAY_ENTRE_CLIQUES_S)


def _texto_campo_view_e_valor(page: Page, campo_id: str) -> dict:
    return page.evaluate(
        """(id) => {
            const el = document.getElementById(id);
            if (!el) return { view: '', value: '' };
            const view = el.parentElement && el.parentElement.querySelector('p.viewing-input');
            return {
                view: view ? String(view.innerText || '').trim() : '',
                value: String(el.value || '').trim()
            };
        }""",
        campo_id,
    )


def ler_natureza_operacao(page: Page) -> str:
    dados = _texto_campo_view_e_valor(page, "natureza")
    return (dados.get("view") or dados.get("value") or "").strip()


def ler_desconto_atual(page: Page) -> dict:
    dados = _texto_campo_view_e_valor(page, "desconto")
    view = (dados.get("view") or "").strip()
    value = (dados.get("value") or "").strip()
    return {
        "view": view,
        "value": value,
        "texto": view or value,
    }


def ler_totais(page: Page) -> dict:
    return page.evaluate(
        """() => {
            const val = (id) => {
                const el = document.getElementById(id);
                return el ? String(el.value || '') : '';
            };
            const viewDesconto = (() => {
                const el = document.getElementById('desconto');
                const view = el && el.parentElement && el.parentElement.querySelector('p.viewing-input');
                return view ? String(view.innerText || '').trim() : '';
            })();
            const viewTotal = (() => {
                const wrap = document.querySelector('label[for="divTotal"]');
                const view = wrap && wrap.parentElement && wrap.parentElement.querySelector('p.viewing-input');
                return view ? String(view.innerText || '').trim() : '';
            })();
            return {
                subtotal: val('subtotal'),
                total: val('total'),
                divTotal: val('divTotal'),
                desconto: val('desconto'),
                viewDesconto,
                viewTotal,
                frete: val('frete'),
                valorIPI: val('valorIPI'),
                valorICMSSubst: val('valorICMSSubst'),
                outrasDespesas: val('outrasDespesas')
            };
        }"""
    )


def clicar_editar(page: Page) -> None:
    btn = page.locator("button.btn-edicao-item").first
    btn.wait_for(state="visible", timeout=TIMEOUT_ACAO_MS)
    btn.click(timeout=TIMEOUT_ACAO_MS)
    page.locator("#desconto").wait_for(state="visible", timeout=TIMEOUT_ACAO_MS)
    page.locator("#desconto").scroll_into_view_if_needed()
    time.sleep(DELAY_ENTRE_CLIQUES_S)


def preencher_desconto(page: Page, texto: str) -> None:
    page.evaluate(
        """(valor) => {
            const el = document.getElementById('desconto');
            if (!el) throw new Error('Campo #desconto nao encontrado');
            el.scrollIntoView({ block: 'center' });
            el.focus();
            el.value = valor;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            if (window.jQuery) {
                window.jQuery(el).val(valor).trigger('change');
            }
            if (typeof totalGeral === 'function') totalGeral();
        }""",
        texto,
    )
    time.sleep(DELAY_APOS_CALCULO_S)


def percentual_maximo(subtotal: float, extras: float, minimo: float) -> float:
    if subtotal <= 0:
        return 0.0
    alvo_produtos = minimo - extras
    if alvo_produtos <= 0:
        return 99.99
    if alvo_produtos >= subtotal:
        return 0.0
    bruto = (1.0 - (alvo_produtos / subtotal)) * 100.0
    return max(0.0, math.floor(bruto * 100.0) / 100.0)


def confirmar_dialogos(page: Page) -> None:
    seletores = [
        ".bootbox.modal.in button[data-bb-handler='confirm']",
        ".bootbox.modal.show button[data-bb-handler='confirm']",
        ".bootbox.modal.in .btn-primary",
        ".bootbox.modal.show .btn-primary",
        ".modal.in .modal-footer .btn-primary",
        ".modal.show .modal-footer .btn-primary",
    ]
    for sel in seletores:
        loc = page.locator(sel)
        try:
            if loc.count() == 0:
                continue
            visivel = loc.last
            if visivel.is_visible():
                texto = (visivel.inner_text() or "").strip()
                log.info("Confirmando dialogo: %s", texto or sel)
                visivel.click(timeout=3_000)
                time.sleep(0.4)
                return
        except Exception:
            continue


def ler_alerta(page: Page) -> str:
    return page.evaluate(
        """() => {
            const nos = document.querySelectorAll(
                '.bootbox .modal-body, .modal.in .modal-body, .modal.show .modal-body, #bs-modal .modal-body, .alert'
            );
            for (const n of nos) {
                const t = (n.innerText || '').trim();
                if (t) return t.slice(0, 400);
            }
            return '';
        }"""
    )


def aplicar_desconto(page: Page, p_usuario: float, minimo: float) -> tuple[float, float]:
    totais = ler_totais(page)
    subtotal = parse_numero_br(totais.get("subtotal"))
    total_atual = parse_numero_br(totais.get("total") or totais.get("viewTotal"))
    desconto_atual = parse_numero_br(totais.get("desconto") or totais.get("viewDesconto"))
    extras = total_atual - subtotal + desconto_atual

    p_max = percentual_maximo(subtotal, extras, minimo)
    p_usar = min(p_usuario, p_max)
    if p_usar <= 0:
        raise RuntimeError(
            f"Nao e possivel aplicar desconto sem ficar abaixo de {minimo:.2f} "
            f"(subtotal={subtotal:.2f}, total={total_atual:.2f})."
        )

    texto = formatar_percentual(p_usar)
    preencher_desconto(page, texto)

    total_depois = parse_numero_br(page.evaluate("() => (document.getElementById('divTotal') || {}).value || ''"))
    tentativas = 0
    while total_depois > 0 and total_depois < minimo - 0.001 and p_usar > 0.01 and tentativas < 25:
        p_usar = max(0.0, math.floor((p_usar - 0.01) * 100.0) / 100.0)
        texto = formatar_percentual(p_usar)
        log.info("Total %.2f abaixo do minimo; reduzindo para %s", total_depois, texto)
        preencher_desconto(page, texto)
        total_depois = parse_numero_br(
            page.evaluate("() => (document.getElementById('divTotal') || {}).value || ''")
        )
        tentativas += 1

    if total_depois < minimo - 0.001:
        raise RuntimeError(
            f"Total calculado {total_depois:.2f} ficou abaixo do minimo {minimo:.2f} "
            f"mesmo apos ajustar o percentual."
        )

    if abs(p_usar - p_usuario) > 0.001:
        log.info(
            "Percentual ajustado de %s para %s para manter total >= %.2f (total calculado=%.2f)",
            formatar_percentual(p_usuario),
            formatar_percentual(p_usar),
            minimo,
            total_depois,
        )
    else:
        log.info("Desconto %s aplicado. Total calculado=%.2f", texto, total_depois)

    return p_usar, total_depois


def clicar_salvar(page: Page) -> None:
    btn = page.locator("#botaoSalvar")
    btn.scroll_into_view_if_needed()
    btn.wait_for(state="visible", timeout=TIMEOUT_ACAO_MS)
    btn.click(timeout=TIMEOUT_ACAO_MS)
    log.info("Clicou em salvar.")
    time.sleep(0.5)
    confirmar_dialogos(page)


def _em_modo_visualizacao(page: Page) -> bool:
    return page.evaluate(
        """() => {
            if (document.body.classList.contains('wait-block-open')) return false;
            const desconto = document.getElementById('desconto');
            if (!desconto) return false;
            const descontoOculto = window.getComputedStyle(desconto).display === 'none';
            const editar = document.querySelector('button.btn-edicao-item');
            if (!editar) return false;
            const s = window.getComputedStyle(editar);
            const editarVisivel = s.display !== 'none' && s.visibility !== 'hidden';
            return descontoOculto && editarVisivel;
        }"""
    )


def aguardar_salvo(page: Page) -> None:
    inicio = time.time()
    viu_espera = False
    while (time.time() - inicio) * 1000 < TIMEOUT_SALVAR_MS:
        alerta = ler_alerta(page)
        if alerta and re.search(r"erro|falha|nao foi possivel|não foi possível", alerta, re.I):
            raise RuntimeError(f"Alerta ao salvar: {alerta}")

        confirmar_dialogos(page)

        if page.evaluate("() => document.body.classList.contains('wait-block-open')"):
            viu_espera = True

        salvo_disabled = page.evaluate(
            "() => { const b = document.getElementById('botaoSalvar'); return !!(b && b.disabled); }"
        )
        if salvo_disabled:
            viu_espera = True

        if _em_modo_visualizacao(page) and (viu_espera or (time.time() - inicio) > 2.0):
            log.info("Pedido salvo; voltou ao detalhe.")
            time.sleep(DELAY_ENTRE_CLIQUES_S)
            return
        time.sleep(0.4)

    raise RuntimeError("Timeout aguardando o salvamento do pedido.")


def processar_pedido(page: Page, pedido: dict, p_usuario: float, minimo: float, simular: bool) -> str:
    id_venda = pedido["id"]
    rotulo = f"N {pedido.get('numero') or '?'} id={id_venda} ({pedido.get('cliente') or ''})".strip()
    log.info("--- %s | total_grid=%s | situacao=%s ---", rotulo, pedido.get("valor"), pedido.get("situacao"))

    if (pedido.get("podeEditar") or "S").upper() == "N":
        log.info("Pedido sem permissao de edicao. Pulando.")
        return "sem_edicao"

    abrir_pedido(page, pedido)

    natureza = ler_natureza_operacao(page)
    if natureza_bloqueia_desconto(natureza):
        log.info("Natureza da operacao bloqueia desconto (%s). Pulando.", natureza)
        voltar_para_lista(page)
        return "natureza_terceiros"

    desconto = ler_desconto_atual(page)
    if desconto_eh_percentual(desconto.get("view"), desconto.get("value")):
        log.info("Desconto ja esta em percentual (%s). Pulando.", desconto.get("texto"))
        voltar_para_lista(page)
        return "ja_tinha_percentual"

    if desconto.get("texto"):
        log.info("Desconto em valor (%s) sera substituido pelo percentual.", desconto.get("texto"))

    totais = ler_totais(page)
    total_atual = parse_numero_br(totais.get("total") or totais.get("viewTotal"))
    if total_atual <= minimo + 0.001:
        log.info("Total da venda %.2f ja esta no minimo. Pulando.", total_atual)
        voltar_para_lista(page)
        return "total_minimo"

    if simular:
        subtotal = parse_numero_br(totais.get("subtotal"))
        desconto_atual = parse_numero_br(totais.get("desconto") or totais.get("viewDesconto"))
        extras = total_atual - subtotal + desconto_atual
        p_max = percentual_maximo(subtotal, extras, minimo)
        p_usar = min(p_usuario, p_max)
        log.info(
            "SIMULACAO: aplicaria %s (pedido %s, total atual %.2f, desconto atual=%s). Nao salvou.",
            formatar_percentual(p_usar),
            rotulo,
            total_atual,
            desconto.get("texto") or "vazio",
        )
        voltar_para_lista(page)
        return "simulado"

    clicar_editar(page)
    p_usado, total_final = aplicar_desconto(page, p_usuario, minimo)
    clicar_salvar(page)
    aguardar_salvo(page)
    log.info("Salvo %s com %s | total final %.2f", rotulo, formatar_percentual(p_usado), total_final)
    voltar_para_lista(page)
    return "aplicado"


def ler_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aplica desconto percentual nos pedidos visiveis do Olist.")
    parser.add_argument("--percentual", help="Percentual de desconto (ex: 10 ou 10,5).")
    parser.add_argument(
        "--minimo",
        type=float,
        default=TOTAL_MINIMO_PADRAO,
        help="Total minimo da venda apos o desconto (padrao: 10.00).",
    )
    parser.add_argument(
        "--verificar",
        action="store_true",
        help="Somente testa a conexao, encontra a aba e conta a grid; nao clica em nada.",
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Abre cada pedido, informa o que faria e volta sem editar/salvar.",
    )
    return parser.parse_args()


def main() -> int:
    args = ler_argumentos()
    log.info("=" * 60)
    log.info("Robo Olist - desconto em pedidos")
    log.info("Log: %s", ARQUIVO_LOG)
    log.info("CDP: %s", CDP_URL)
    log.info("Ctrl+C para interromper")
    log.info("=" * 60)

    percentual: float | None = None
    if not args.verificar:
        bruto = args.percentual
        if not bruto:
            try:
                bruto = input("Percentual de desconto (ex: 10): ").strip()
            except EOFError:
                bruto = ""
        try:
            percentual = parse_percentual(bruto)
        except ValueError as e:
            log.error("%s", e)
            return 1
        log.info("Percentual informado: %s", formatar_percentual(percentual))
        log.info("Total minimo da venda: %.2f", args.minimo)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            log.error(
                "Nao conectou no Chrome em %s.\n"
                "Feche o Chrome, rode iniciar_chrome_olist.bat, "
                "filtre os pedidos e tente de novo.\nDetalhe: %s",
                CDP_URL,
                e,
            )
            return 1

        page = encontrar_pagina_pedidos(browser)
        page.set_default_timeout(TIMEOUT_ACAO_MS)

        if args.verificar:
            if not na_lista(page):
                log.info("Aba nao esta na lista; voltando para contar os pedidos.")
                voltar_para_lista(page)
            info_pag = ler_info_paginacao(page)
            pedidos = listar_pedidos_visiveis(page)
            log.info(
                "VERIFICACAO OK: aba conectada, pagina=%s/%s, pedidos visiveis=%s, tem_proxima=%s",
                info_pag.get("paginaAtual"),
                info_pag.get("totalPaginas"),
                len(pedidos),
                info_pag.get("temProxima"),
            )
            log.info("Nenhum clique de edicao/salvar foi executado.")
            return 0

        try:
            if not na_lista(page):
                log.info("Tela de detalhe aberta; voltando para a lista.")
                voltar_para_lista(page)

            contagem = {
                "aplicado": 0,
                "ja_tinha_percentual": 0,
                "natureza_terceiros": 0,
                "total_minimo": 0,
                "sem_edicao": 0,
                "simulado": 0,
                "erro": 0,
            }
            erros_seguidos = 0
            pagina_grid = 0
            pedidos_processados = 0
            parar = False

            while not parar:
                if not na_lista(page):
                    voltar_para_lista(page)

                info_pag = ler_info_paginacao(page)
                pedidos = listar_pedidos_visiveis(page)
                if not pedidos:
                    if pagina_grid == 0:
                        log.info("Nenhum pedido visivel na grid. Encerrando.")
                    break

                pagina_grid += 1
                log.info(
                    "=== Pagina %s/%s | pedidos na tela: %s ===",
                    info_pag.get("paginaAtual"),
                    info_pag.get("totalPaginas"),
                    len(pedidos),
                )

                for i, pedido in enumerate(pedidos, start=1):
                    pedidos_processados += 1
                    log.info(
                        "Pedido %s/%s (pagina %s/%s)",
                        i,
                        len(pedidos),
                        info_pag.get("paginaAtual"),
                        info_pag.get("totalPaginas"),
                    )
                    try:
                        status = processar_pedido(
                            page, pedido, percentual or 0.0, args.minimo, args.simular
                        )
                        contagem[status] = contagem.get(status, 0) + 1
                        erros_seguidos = 0
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        contagem["erro"] += 1
                        erros_seguidos += 1
                        log.exception("Erro no pedido %s: %s", pedido.get("id"), e)
                        try:
                            voltar_para_lista(page)
                        except Exception:
                            log.warning("Falha ao voltar para a lista apos erro.")
                        if erros_seguidos >= MAX_ERROS_SEGUIDOS:
                            log.error("Muitos erros seguidos. Parando.")
                            parar = True
                            break

                if parar:
                    break

                if not info_pag.get("temProxima"):
                    log.info("Ultima pagina do filtro concluida.")
                    break

                if not ir_para_proxima_pagina(page):
                    log.warning("Nao foi possivel avancar para a proxima pagina. Encerrando.")
                    break

            log.info("Pedidos visitados: %s | paginas processadas: %s", pedidos_processados, pagina_grid)
            log.info(
                "Resumo: aplicados=%s | ja_tinham_percentual=%s | natureza_terceiros=%s | "
                "total_minimo=%s | sem_edicao=%s | simulados=%s | erros=%s",
                contagem["aplicado"],
                contagem["ja_tinha_percentual"],
                contagem["natureza_terceiros"],
                contagem["total_minimo"],
                contagem["sem_edicao"],
                contagem["simulado"],
                contagem["erro"],
            )
        except KeyboardInterrupt:
            log.info("Interrompido pelo usuario (Ctrl+C).")

    log.info("=" * 60)
    log.info("Fim. Log salvo em: %s", ARQUIVO_LOG)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
