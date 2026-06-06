from database import (
    get_all_participantes, get_palpites_by_participante,
    get_classificacao_palpite, get_placares_reais, get_classificacao_real,
    USE_PG,
)

JOGOS = {
    'jogo1': {'data': '13/06', 'adversario': 'Marrocos', 'flag': '🇲🇦'},
    'jogo2': {'data': '19/06', 'adversario': 'Haiti',    'flag': '🇭🇹'},
    'jogo3': {'data': '24/06', 'adversario': 'Escócia',  'flag': '🏴󠁧󠁢󠁳󠁣󠁴󠁿'},
}

PONTOS_PLACAR_EXATO   = 50
PONTOS_COLOCADO_IND   = 30
PONTOS_GABARITO_TOTAL = 100


def _get_todos_palpites_bulk() -> tuple[dict, dict]:
    """
    Busca palpites e classificações de todos os participantes em 2 queries
    em vez de 2×N queries.
    Retorna:
      palpites_map:  {pid: {jogo: (gb, ga)}}
      classif_map:   {pid: (1º, 2º, 3º, 4º)}
    """
    if USE_PG:
        from database import _get_conn_ctx, _run
        with _get_conn_ctx() as conn:
            rows_p = _run(conn,
                "SELECT participante_id, jogo, gols_brasil, gols_adversario FROM palpites"
            )
            rows_c = _run(conn,
                "SELECT participante_id, primeiro, segundo, terceiro, quarto FROM classificacao_palpites"
            )
    else:
        from database import _get_conn
        conn = _get_conn()
        rows_p = conn.execute(
            "SELECT participante_id, jogo, gols_brasil, gols_adversario FROM palpites"
        ).fetchall()
        rows_c = conn.execute(
            "SELECT participante_id, primeiro, segundo, terceiro, quarto FROM classificacao_palpites"
        ).fetchall()

    palpites_map: dict = {}
    for r in rows_p:
        pid, jogo, gb, ga = r[0], r[1], r[2], r[3]
        palpites_map.setdefault(pid, {})[jogo] = (gb, ga)

    classif_map: dict = {}
    for r in rows_c:
        pid = r[0]
        classif_map[pid] = (r[1], r[2], r[3], r[4])

    return palpites_map, classif_map


def score_participant(pid, placares_reais, classificacao_real, palpites, classif_palpite):
    """Calcula pontuação de um participante usando dados já carregados."""
    total  = 0
    detail = {}

    # ── Placares ──────────────────────────────────────────
    for jogo in ['jogo1', 'jogo2', 'jogo3']:
        real = placares_reais.get(jogo, {})
        palpite_jogo = palpites.get(jogo)

        if not real.get('encerrado'):
            detail[jogo] = {
                'pontos': None,
                'status': 'pendente',
                'palpite': palpite_jogo if palpite_jogo else [],
                'real': []
            }
            continue

        if not palpite_jogo:
            detail[jogo] = {
                'pontos': 0,
                'status': 'sem_palpite',
                'palpite': [],
                'real': (real.get('brasil'), real.get('adversario'))
            }
            continue

        pb, pa = palpite_jogo
        rb, ra = real['brasil'], real['adversario']

        if pb == rb and pa == ra:
            pts    = PONTOS_PLACAR_EXATO
            status = 'exato'
        else:
            pts    = 0
            status = 'errado'

        total += pts
        detail[jogo] = {
            'pontos': pts,
            'status': status,
            'palpite': (pb, pa),
            'real': (rb, ra)
        }

    # ── Classificação ─────────────────────────────────────
    classif_pts    = 0
    classif_status = {}

    if classif_palpite and len(classificacao_real) == 4:
        palpite_lista = list(classif_palpite)
        real_lista    = [classificacao_real[i] for i in range(1, 5)]

        acertos_ind = 0
        for i in range(4):
            if palpite_lista[i].strip().upper() == real_lista[i].strip().upper():
                acertos_ind += 1
                classif_status[i + 1] = 'acerto'
                classif_pts += PONTOS_COLOCADO_IND
            else:
                classif_status[i + 1] = 'errado'

        if acertos_ind == 4:
            classif_pts += PONTOS_GABARITO_TOTAL
            classif_status['gabarito'] = True
        else:
            classif_status['gabarito'] = False

    elif classif_palpite and len(classificacao_real) < 4:
        classif_status = {'pendente': True}

    total += classif_pts
    detail['classificacao'] = {
        'pontos': classif_pts,
        'status': classif_status,
        'palpite': list(classif_palpite) if classif_palpite else [],
        'real':    [classificacao_real.get(i, '') for i in range(1, 5)],
    }

    return total, detail


def calculate_scores():
    """Retorna lista de participantes com pontuação, usando bulk queries."""
    # 4 queries no total independente do número de participantes
    participantes      = get_all_participantes()
    placares_reais     = get_placares_reais()
    classificacao_real = get_classificacao_real()
    palpites_map, classif_map = _get_todos_palpites_bulk()

    results = []
    for pid, nome, criado_em in participantes:
        palpites       = palpites_map.get(pid, {})
        classif_palpite = classif_map.get(pid)
        total, detail  = score_participant(
            pid, placares_reais, classificacao_real, palpites, classif_palpite
        )
        results.append({
            'id':        pid,
            'nome':      nome,
            'total':     total,
            'detail':    detail,
            'criado_em': criado_em,
        })

    results.sort(key=lambda x: (-x['total'], x['criado_em']))
    return results
