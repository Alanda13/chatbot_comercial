from src.database import get_connection

def listar_avaliacoes(limite=5):
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        consulta = """
            SELECT TOP (?) *
            FROM dbo.Avaliacoes
            ORDER BY DataHora DESC
        """
        cursor.execute(consulta, limite)

        colunas = [coluna[0] for coluna in cursor.description]
        registros = cursor.fetchall()

        return [
            dict(zip(colunas, registro))
            for registro in registros
        ]
    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

def obter_resumo_nps():
    """
    Consulta o banco e calcula os principais indicadores gerais de NPS.
    """
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        consulta = """
            SELECT
                COUNT(*) AS TotalRespostas,

                SUM(
                    CASE
                        WHEN TRY_CONVERT(INT, Nota) BETWEEN 9 AND 10
                        THEN 1
                        ELSE 0
                    END
                ) AS TotalPromotores,

                SUM(
                    CASE
                        WHEN TRY_CONVERT(INT, Nota) BETWEEN 7 AND 8
                        THEN 1
                        ELSE 0
                    END
                ) AS TotalNeutros,

                SUM(
                    CASE
                        WHEN TRY_CONVERT(INT, Nota) BETWEEN 0 AND 6
                        THEN 1
                        ELSE 0
                    END
                ) AS TotalDetratores

            FROM dbo.Avaliacoes

            WHERE TRY_CONVERT(INT, Nota) BETWEEN 0 AND 10
        """
        cursor.execute(consulta)
        registro = cursor.fetchone()

        if registro is None:
            return {
                "total_respostas": 0,
                "total_promotores": 0,
                "total_neutros": 0,
                "total_detratores": 0,
                "percentual_promotores": 0,
                "percentual_neutros": 0,
                "percentual_detratores": 0,
                "nps_geral": 0,
            }
        total_respostas = registro[0] or 0
        total_promotores = registro[1] or 0
        total_neutros = registro[2] or 0
        total_detratores = registro[3] or 0

        if total_respostas == 0:
            return {
                "total_respostas": 0,
                "total_promotores": 0,
                "total_neutros": 0,
                "total_detratores": 0,
                "percentual_promotores": 0,
                "percentual_neutros": 0,
                "percentual_detratores": 0,
                "nps_geral": 0,
            }
        percentual_promotores = (
            total_promotores / total_respostas
        ) * 100
        percentual_neutros = (
            total_neutros / total_respostas
        ) * 100
        percentual_detratores = (
            total_detratores / total_respostas
        ) * 100
        nps_geral = (
            percentual_promotores
            - percentual_detratores
        )
        return {
            "total_respostas": total_respostas,
            "total_promotores": total_promotores,
            "total_neutros": total_neutros,
            "total_detratores": total_detratores,
            "percentual_promotores": round(
                percentual_promotores, 2
            ),
            "percentual_neutros": round(
                percentual_neutros, 2
            ),
            "percentual_detratores": round(
                percentual_detratores, 2
            ),
            "nps_geral": round(nps_geral, 2),
        }
    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

###      PARA DESCOBRIR OS NOMES DAS FILIAISSSSSSS
def listar_filiais():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        consulta = """
            SELECT TOP 100 *
            FROM dbo.Filiais
        """
        cursor.execute(consulta)
        colunas = [coluna[0] for coluna in cursor.description]
        registros = cursor.fetchall()

        return [
            dict(zip(colunas, registro))
            for registro in registros
        ]
    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

####   ==== OBTER NPS POR FILIAL =====
def obter_nps_por_filial():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        consulta = """
            SELECT
                F.Id AS FilialId,
                F.Nome AS Filial,

                COUNT(*) AS TotalRespostas,

                SUM(
                    CASE
                        WHEN TRY_CONVERT(INT, A.Nota) BETWEEN 9 AND 10
                        THEN 1
                        ELSE 0
                    END
                ) AS TotalPromotores,

                SUM(
                    CASE
                        WHEN TRY_CONVERT(INT, A.Nota) BETWEEN 7 AND 8
                        THEN 1
                        ELSE 0
                    END
                ) AS TotalNeutros,

                SUM(
                    CASE
                        WHEN TRY_CONVERT(INT, A.Nota) BETWEEN 0 AND 6
                        THEN 1
                        ELSE 0
                    END
                ) AS TotalDetratores

            FROM dbo.Avaliacoes AS A

            INNER JOIN dbo.Filiais AS F
                ON A.FilialId = F.Id

            WHERE TRY_CONVERT(INT, A.Nota) BETWEEN 0 AND 10

            GROUP BY
                F.Id,
                F.Nome

            ORDER BY
                F.Nome
        """
        cursor.execute(consulta)
        registros = cursor.fetchall()
        filiais = []

        for registro in registros:
            filial_id = registro[0]
            filial = registro[1]
            total_respostas = registro[2] or 0
            total_promotores = registro[3] or 0
            total_neutros = registro[4] or 0
            total_detratores = registro[5] or 0

            percentual_promotores = (
                total_promotores / total_respostas
            ) * 100
            percentual_neutros = (
                total_neutros / total_respostas
            ) * 100
            percentual_detratores = (
                total_detratores / total_respostas
            ) * 100
            nps = (
                percentual_promotores
                - percentual_detratores
            )
            filiais.append({
                "filial_id": filial_id,
                "filial": filial,
                "total_respostas": total_respostas,
                "total_promotores": total_promotores,
                "total_neutros": total_neutros,
                "total_detratores": total_detratores,
                "percentual_promotores": round(
                    percentual_promotores, 2
                ),
                "percentual_neutros": round(
                    percentual_neutros, 2
                ),
                "percentual_detratores": round(
                    percentual_detratores, 2
                ),
                "nps": round(nps, 2),
            })
        return filiais
    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()
         
 
###  FUNÇÃO NOVAAAAA
def obter_nps_filial_periodo(
    filial: str,
    data_inicial: str,
    data_final: str,
):
    """
    Calcula os indicadores de NPS de uma filial
    dentro de um período informado.

    Parâmetros:
    - filial: nome da filial.
    - data_inicial: data inicial (YYYY-MM-DD).
    - data_final: data final (YYYY-MM-DD).

    Retorna:
    - filial;
    - total de respostas;
    - total de promotores;
    - total de neutros;
    - total de detratores;
    - percentual de promotores;
    - percentual de neutros;
    - percentual de detratores;
    - NPS.
    """

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        consulta = """
            SELECT
                F.Id AS FilialId,
                F.Nome AS Filial,

                COUNT(*) AS TotalRespostas,

                SUM(
                    CASE
                        WHEN TRY_CONVERT(INT, A.Nota) BETWEEN 9 AND 10
                        THEN 1
                        ELSE 0
                    END
                ) AS TotalPromotores,

                SUM(
                    CASE
                        WHEN TRY_CONVERT(INT, A.Nota) BETWEEN 7 AND 8
                        THEN 1
                        ELSE 0
                    END
                ) AS TotalNeutros,

                SUM(
                    CASE
                        WHEN TRY_CONVERT(INT, A.Nota) BETWEEN 0 AND 6
                        THEN 1
                        ELSE 0
                    END
                ) AS TotalDetratores

            FROM dbo.Avaliacoes AS A

            INNER JOIN dbo.Filiais AS F
                ON A.FilialId = F.Id

            WHERE
                TRY_CONVERT(INT, A.Nota) BETWEEN 0 AND 10
                AND F.Nome = ?
                AND A.DataHora >= ?
                AND A.DataHora < DATEADD(DAY, 1, ?)

            GROUP BY
                F.Id,
                F.Nome
        """

        cursor.execute(
            consulta,
            filial,
            data_inicial,
            data_final,
        )

        registro = cursor.fetchone()

        if registro is None:
            return {
                "filial": filial,
                "data_inicial": data_inicial,
                "data_final": data_final,
                "total_respostas": 0,
                "total_promotores": 0,
                "total_neutros": 0,
                "total_detratores": 0,
                "percentual_promotores": 0,
                "percentual_neutros": 0,
                "percentual_detratores": 0,
                "nps": None,
            }

        filial_id = registro[0]
        nome_filial = registro[1]
        total_respostas = registro[2] or 0
        total_promotores = registro[3] or 0
        total_neutros = registro[4] or 0
        total_detratores = registro[5] or 0

        if total_respostas == 0:
            return {
                "filial_id": filial_id,
                "filial": nome_filial,
                "data_inicial": data_inicial,
                "data_final": data_final,
                "total_respostas": 0,
                "total_promotores": 0,
                "total_neutros": 0,
                "total_detratores": 0,
                "percentual_promotores": 0,
                "percentual_neutros": 0,
                "percentual_detratores": 0,
                "nps": None,
            }

        percentual_promotores = (
            total_promotores / total_respostas
        ) * 100

        percentual_neutros = (
            total_neutros / total_respostas
        ) * 100

        percentual_detratores = (
            total_detratores / total_respostas
        ) * 100

        nps = (
            percentual_promotores
            - percentual_detratores
        )

        return {
            "filial_id": filial_id,
            "filial": nome_filial,
            "data_inicial": data_inicial,
            "data_final": data_final,
            "total_respostas": total_respostas,
            "total_promotores": total_promotores,
            "total_neutros": total_neutros,
            "total_detratores": total_detratores,
            "percentual_promotores": round(
                percentual_promotores,
                2,
            ),
            "percentual_neutros": round(
                percentual_neutros,
                2,
            ),
            "percentual_detratores": round(
                percentual_detratores,
                2,
            ),
            "nps": round(nps, 2),
        }

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

#### CALCULAR NPS POR PERIODO###
def obter_nps_por_periodo(data_inicial, data_final):
    """
    Calcula o NPS dentro de um período informado.

    Parâmetros:
    - data_inicial: data inicial no formato YYYY-MM-DD
    - data_final: data final no formato YYYY-MM-DD

    Retorna:
    - data inicial;
    - data final;
    - total de respostas;
    - NPS do período.
    """
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        consulta = """
            SELECT
                COUNT(*) AS TotalRespostas,

                SUM(
                    CASE
                       WHEN TRY_CONVERT(INT, Nota) BETWEEN 9 AND 10
                       THEN 1
                       ELSE 0
                    END
                ) AS TotalPromotores,

                SUM(
                    CASE
                       WHEN TRY_CONVERT(INT, Nota) BETWEEN 7 AND 8
                       THEN 1
                       ELSE 0
                    END
                ) AS TotalNeutros,

                SUM(
                    CASE
                       WHEN TRY_CONVERT(INT, Nota) BETWEEN 0 AND 6
                       THEN 1
                       ELSE 0
                    END
                ) AS TotalDetratores

            FROM dbo.Avaliacoes

            WHERE
                TRY_CONVERT(INT, Nota) BETWEEN 0 AND 10
                AND DataHora >= ?
                AND DataHora < DATEADD(DAY, 1, ?)
"""
        cursor.execute(
            consulta,
            data_inicial,
            data_final,
        )
        registro = cursor.fetchone()

        total_respostas = registro[0] or 0
        total_promotores = registro[1] or 0
        total_neutros = registro[2] or 0
        total_detratores = registro[3] or 0

        if total_respostas == 0:
            return {
                "data_inicial": data_inicial,
                "data_final": data_final,
                "total_respostas": 0,
                "total_promotores": 0,
                "total_neutros": 0,
                "total_detratores": 0,
                "percentual_promotores": 0,
                "percentual_neutros": 0,
                "percentual_detratores": 0,
                "nps": None,
            }

        percentual_promotores = (
            total_promotores / total_respostas
        ) * 100

        percentual_neutros = (
            total_neutros / total_respostas
        ) * 100

        percentual_detratores = (
            total_detratores / total_respostas
        ) * 100

        nps = (
            percentual_promotores
            - percentual_detratores
        )

        return {
            "data_inicial": data_inicial,
            "data_final": data_final,
            "total_respostas": total_respostas,
            "total_promotores": total_promotores,
            "total_neutros": total_neutros,
            "total_detratores": total_detratores,
            "percentual_promotores": round(
                percentual_promotores,
                2,
            ),
            "percentual_neutros": round(
                percentual_neutros,
                2,
            ),
            "percentual_detratores": round(
                percentual_detratores,
                2,
            ),
            "nps": round(nps, 2),
        }
    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

### =========== COMPARAÇÃO ENTRE PERÍODOS =============
def comparar_nps_entre_periodos(
        data_inicial_atual,
        data_final_atual,
        data_inicial_anterior,
        data_final_anterior,
):
    """
    Comparar o NPS entre dois períodos distintos.
    Retorna:
    - NPS do período atual;
    - NPS do período anterior;
    - variação em pontos;
    - situação da variação.
    """
    periodo_atual = obter_nps_por_periodo(
        data_inicial_atual,
        data_final_atual,
    )
    periodo_anterior = obter_nps_por_periodo(
        data_inicial_anterior,
        data_final_anterior,
    )
    nps_atual = periodo_atual["nps"]
    nps_anterior = periodo_anterior["nps"]

    if nps_atual is None or nps_anterior is None:
        return {
            "periodo_atual": periodo_atual,
            "periodo_anterior": periodo_anterior,
            "variacao": None,
            "situacao": "Não foi possível comparar os períodos",
        }
    variacao = nps_atual - nps_anterior 

    if variacao > 0:
        situacao = "O NPS aumentou"

    elif variacao < 0:
        situacao = "O NPS diminuiu"

    else:
        situacao = "O NPS permaneceu igual"

    return {
        "periodo_atual": periodo_atual,
        "periodo_anterior": periodo_anterior,
        "variacao": round(variacao, 2),
        "situacao": situacao,
    }


