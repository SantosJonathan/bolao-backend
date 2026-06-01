from database import (
    get_all_participantes, get_palpites_by_participante,
    get_classificacao_palpite, get_placares_reais, get_classificacao_real
)

JOGOS = {
    'jogo1': {'data': '13/06', 'adversario': 'Marrocos', 'flag': '🇲🇦'},
    'jogo2': {'data': '19/06', 'adversario': 'Haiti',    'flag': '🇭🇹'},
    'jogo3': {'data': '24/06', 'adversario': 'Escócia',  'flag': '🏴󠁧󠁢󠁳󠁣󠁴󠁿'},
}

TIMES_GRUPO = ['Brasil', 'Marrocos', 'Haiti', 'Escócia']

PONTOS_PLACAR_EXATO   = 50
PONTOS_COLOCADO_IND   = 30
PONTOS_GABARITO_TOTAL = 100


def score_participant(pid):
    placares_reais    = get_placares_reais()
    classificacao_real = get_classificacao_real()
    palpites          = get_palpites_by_participante(pid)
    classif_palpite   = get_classificacao_palpite(pid)

    total  = 0
    detail = {}

    # ── Placares ──────────────────────────────────────────
    for jogo in ['jogo1', 'jogo2', 'jogo3']:
        real = placares_reais.get(jogo, {})
        if not real.get('encerrado'):
            detail[jogo] = {'pontos': None, 'status': 'pendente'}
            continue
        if jogo not in palpites:
            detail[jogo] = {'pontos': 0, 'status': 'sem_palpite'}
            continue
        pb, pa = palpites[jogo]
        rb, ra = real['brasil'], real['adversario']
        if pb == rb and pa == ra:
            pts = PONTOS_PLACAR_EXATO
            status = 'exato'
        else:
            pts = 0
            status = 'errado'
        total += pts
        detail[jogo] = {'pontos': pts, 'status': status,
                        'palpite': (pb, pa), 'real': (rb, ra)}

    # ── Classificação ─────────────────────────────────────
    classif_pts    = 0
    classif_status = {}

    if classif_palpite and len(classificacao_real) == 4:
        palpite_lista = list(classif_palpite)   # [1º,2º,3º,4º]
        real_lista    = [classificacao_real[i] for i in range(1, 5)]

        # Check individual positions (case-insensitive — formulário salva em MAIÚSCULAS,
        # admin salva com capitalização normal, ex: "MARROCOS" == "Marrocos")
        acertos_ind = 0
        for i in range(4):
            if palpite_lista[i].strip().upper() == real_lista[i].strip().upper():
                acertos_ind += 1
                classif_status[i+1] = 'acerto'
                classif_pts += PONTOS_COLOCADO_IND
            else:
                classif_status[i+1] = 'errado'

        # Full gabarito bonus
        if acertos_ind == 4:
            classif_pts += PONTOS_GABARITO_TOTAL   # total = 4×30 + 100 = 220
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
    """Returns list of (nome, total_pts, detail) sorted by pts desc."""
    participantes = get_all_participantes()
    results = []
    for pid, nome, criado_em in participantes:
        total, detail = score_participant(pid)
        results.append({
            'id': pid,
            'nome': nome,
            'total': total,
            'detail': detail,
            'criado_em': criado_em,
        })
    results.sort(key=lambda x: (-x['total'], x['criado_em']))
    return results
