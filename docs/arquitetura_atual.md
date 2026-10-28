# Arquitetura do motor de dados genérico — Chatbot Comercial

Status: em migração. Este documento descreve o que **já está implementado e
rodando** (testado contra dados reais), separado do que **ainda falta**.

## Por que essa mudança

Antes, cada pergunta comercial virava uma ferramenta Python nova e específica
(`consultar_indicadores_faturamento`, `consultar_metas`,
`consultar_crescimento_abaixo_meta`...). Isso não escala: o projeto real
prevê ~7 indicadores comerciais, e perguntas que cruzam mais de um
("quais filiais cresceram mas estão abaixo da meta") exigiriam programar cada
combinação nova à mão.

Objetivo: em vez de ensinar a IA "quando o usuário perguntar X, faça Y",
dar a ela **dados + capacidades de análise + regras de negócio + limites**, e
deixar a IA montar o caminho — incluindo perguntas que ninguém programou
especificamente.

## Fluxo atual

```
IA (interpreta a pergunta)
   |  gera um JSON: {indicador, periodo, filtros, agrupar_por,
   |                  comparar_com, filtros_calculados}
   v
ORQUESTRADOR  (src/orquestrador.py)
   |  valida a consulta contra o catálogo
   v
MOTOR DE DADOS
   +-- pandas (carrega o CSV do indicador, via catalogo.py)
   +-- filtros (filial/RCA/supervisor resolvidos por nome, período resolvido)
   +-- groupby/agregação (genérico, guiado pelo catálogo)
   v
MOTOR DE MÉTRICAS  (src/motor_metricas.py)
   |  fórmulas puras: % atingimento de meta, crescimento, falta pra
   |  meta... nunca calculadas pela IA
   v
resultado (dict)
   v
IA  (formata a resposta em texto — e futuramente a tabela do app.py)
```

Uma ferramenta genérica (`consultar_dados_comerciais`) substitui o que seriam
várias ferramentas específicas — hoje ela cobre todos os indicadores que
têm fonte de dado conectada, inclusive o NPS (que vem de SQL, não de CSV).

## As peças, uma por uma

- **`src/catalogo.py`** — fonte única de verdade sobre o que existe no
  sistema. Pra cada indicador: qual função Python carrega o dado bruto, quais
  campos ele tem (e como agregar — soma, média...), quais dimensões dá pra
  filtrar/agrupar, fórmulas derivadas (ex: `% atingimento` a partir de
  `faturamento_realizado` e `valor_meta`), e como cada campo aparece numa
  tabela (`"exibicao"`: tipo, rótulo, quando aparece). Um indicador novo com
  dado real = uma entrada nova aqui — não um arquivo novo de ferramenta, nem
  um bloco novo de tabela em `app.py`.
- **`src/motor_metricas.py`** — funções puras (sem banco, sem IA): `%
  atingimento de meta`, `% desconto`, `% inadimplência`, `crescimento`,
  `valor faltante`, `necessidade diária`, `participação`, `ranking`.
- **`src/orquestrador.py`** — o motor genérico: valida a consulta contra o
  catálogo, resolve período (`mes_atual`, `personalizado`...), busca os
  dados, filtra (reaproveitando a resolução de nome de filial/RCA/supervisor
  que já existia nas ferramentas antigas), agrupa, aplica as fórmulas
  derivadas e filtros sobre a métrica já calculada (ex: "só quem bateu a
  meta"), e sabe comparar dois períodos calculando crescimento sozinho.
- **`src/indicador_tools.py` + `src/tool_manager.py`** — ponte: registra
  `consultar_dados_comerciais` como ferramenta que a IA pode chamar, com a
  lista de indicadores disponíveis gerada automaticamente a partir do
  catálogo (não precisa editar a descrição à mão quando um indicador novo é
  conectado).

## O que já foi migrado (testado contra dado real)

| Indicador | Fonte | Status |
|---|---|---|
| `faturamento` (mensal/anual) | CSV rotina 8280 | ✅ conectado, com `toneladas` calculado |
| `faturamento_diario` | CSV rotina 8302 | ✅ conectado |
| `meta` (faturamento) | mesmo CSV 8280 | ✅ conectado, com `%atingimento`, `falta_para_meta` e `necessidade_diaria` (mês atual) calculados |
| `nps` | Azure SQL (85 mil respostas, carregadas inteiras pro pandas) | ✅ conectado — ver seção "NPS no motor genérico" |
| `meta_tonelada` | CSV do TARGIT | ✅ conectado — motor genérico ganhou suporte a "campo único por combinação de colunas" (`unico_por`), que resolve a duplicação da meta por filial sem hackear nada específico desse indicador |

Capacidades do motor genérico validadas contra dado real (comparando com o
resultado das ferramentas antigas linha por linha, não só "parece certo"):
- valores simples e agrupados de faturamento/meta batem exatamente;
- `toneladas` (faturamento) bate com o cálculo antigo (peso ÷ 1000);
- comparação mês a mês entre 2+ anos (`agrupar_por: ["mes", "ano"]`) calcula
  `percentual_ano_anterior`/`diferenca_ano_anterior` idêntico ao que
  `consultar_metas` calculava — 24 combinações de mês/ano testadas, todas
  batendo;
- `necessidade_diaria` só aparece no mês/ano atual, igual à ferramenta antiga;
- testado end-to-end com a IA de verdade (não só chamando a função Python
  direto): 9 perguntas reais, todas escolhendo a ferramenta certa e com a
  resposta correta, incluindo "compare a meta mês a mês entre 2024 e 2025" e
  "quantas toneladas Timon vendeu em 2025".

## Como o motor passou a lidar com "campo repetido por linha" (meta_tonelada)

A base de meta de tonelada tem uma coluna ("Meta Tonelada - Filial") que se
repete em toda linha de RCA da mesma filial/mês — somar direto multiplicaria
o valor pela quantidade de RCAs. Em vez de resolver isso só pra esse
indicador, o catálogo ganhou uma opção genérica: um campo pode declarar
`"unico_por": (colunas...)`, e o motor descarta as linhas duplicadas
**dentro de cada grupo da consulta** antes de somar — funciona agrupando
por filial, por RCA, por mês, ou sem agrupar nenhum, sem caso especial por
combinação. Um detalhe que só apareceu ao testar: o dedup precisa
considerar a combinação de colunas do agrupamento pedido + a chave do
"unico_por" juntas — deduplicar só pela chave, globalmente, e depois
agrupar por RCA (uma coluna fora da chave) fazia o valor "sumir" pra todo
RCA menos um. Corrigido e coberto por teste antes de conectar o indicador
de verdade. Confirmado com 6 combinações de filtro/agrupamento contra a
ferramenta antiga, todas batendo exatamente.

De quebra, achei e corrigi outro detalhe ao conectar esse indicador: "rca"
é código numérico nas outras bases, mas é NOME (texto) na base de meta de
tonelada — o motor tentava converter pra número sempre; agora só converte
quando dá certo, senão trata como texto.

## RCA: nome automático + filtro "só quem tem meta cadastrada"

Duas lacunas reais que você achou testando "faturamento por RCA": (1) o
resultado só trazia o código, nunca o nome do vendedor; (2) sem filtro de
RCA explícito, vinham TODOS os códigos que já faturaram — incluindo contas
genéricas/contábeis (ex: "FERRONORTE COM DE FERRAGENS LTDA-F07-TIB"), não
só vendedores de verdade. As ferramentas antigas tinham as duas coisas
resolvidas; ficaram pra trás na migração.

Corrigido de forma genérica pros 3 indicadores que usam RCA de verdade
(`faturamento`, `faturamento_diario`, `meta`):
- `rca_nome_mapa` no catálogo: quando agrupa por "rca", o motor busca o
  nome automaticamente (reaproveita `construir_mapa_rca_nome`, já
  existente).
- `rca_requer_meta_cadastrada`: quando agrupa por "rca" e a IA NÃO
  especificou RCA nenhum, o motor restringe aos códigos com meta
  cadastrada na base de metas — mesma regra de negócio das ferramentas
  antigas, mas compartilhada entre indicadores (a definição de "RCA de
  verdade" mora só na base de metas, não é duplicada por indicador). Se a
  IA pedir um RCA específico, ele aparece mesmo sem meta — o filtro só
  entra quando ninguém foi pedido.

Validado: 22 RCAs de Tibiri batendo exatamente com `listar_rcas_filial`
(a ferramenta antiga, usada como referência antes de ser apagada — ver
seção abaixo) quando os dois consultam o mesmo período. Também achei que,
com filtro de ano, a versão nova fica mais precisa que a antiga: a antiga
ignorava o ano ao checar "tem meta cadastrada" (somava todos os 6 anos
disponíveis juntos); a nova considera só o ano perguntado.

**Bug real achido depois, testando "quais RCAs cada filial tem":**
`_rcas_com_meta_cadastrada` somava a meta de cada código em TODAS as
filiais da consulta juntas, não por filial. Um código genérico
reaproveitado em várias filiais como conta contábil (ex: código 1,
"COMERCIAL FERRONORTE LTDA-F01-MATRIZ", meta de verdade só em Campos
Sales) "vazava": bastava ter meta em UMA filial da consulta pra contar
como RCA válido em TODAS as outras, mesmo com meta zero nelas — só
aparecia quando a pergunta trazia várias filiais de uma vez (uma
filial só, filtrada, já calculava certo). Corrigido: a validade agora é
por par (filial, código) — `_rcas_com_meta_cadastrada` agrupa por
`["FILIAL", "COD_RCA"]`, e o filtro em `buscar_dados_brutos` usa
`pd.MultiIndex` nas duas colunas. Conferido: o novo resultado bate
exatamente (nenhum RCA de menos, nenhum a mais) com a lista calculada de
forma independente, filial por filial, a partir do CSV — e confirmei que,
em 2025, nenhum código tem meta de verdade em mais de uma filial (então a
correção só removeu vazamentos, nunca um RCA legítimo).

## As últimas 2 ferramentas específicas de meta, eliminadas

Você perguntou por que `consultar_crescimento_abaixo_meta` e
`listar_rcas_filial` continuavam separadas, já que isso contraria o
objetivo da migração. Tinha razão — as duas já podiam ter sido feitas pela
ferramenta genérica, só faltava uma peça:

- **`listar_rcas_filial`**: não precisava de nada novo — o filtro
  automático "só RCA com meta cadastrada" (seção acima) já resolve
  sozinho. `indicador: meta`, `agrupar_por: [rca]`, `filtros: {filial:
  [...]}` já devolve exatamente a lista certa, com nome.
- **`consultar_crescimento_abaixo_meta`**: faltava o motor genérico saber
  comparar "ano X" com "ano X−1" pra um ano qualquer (não só períodos
  prontos como "mês atual"/"mês anterior"). Adicionei um valor novo de
  `comparar_com`: `"ano_anterior_ao_filtro"` — usa o(s) ano(s) que a
  própria consulta já filtrou, menos 1. Combinado com `filtros_calculados`
  (cresceu E está abaixo da meta), a pergunta vira uma consulta normal,
  sem ferramenta própria.

**Dois bugs reais achei e corrigi durante essa parte** (confirmados contra
a ferramenta antiga antes de apagá-la, igual sempre):
1. O conjunto de "RCAs válidos" (só quem tem meta) estava sendo calculado
   separadamente pro ano atual E pro ano de comparação — um RCA com meta
   em 2025 mas não em 2024 perdia o faturamento de 2024 inteiro, fazendo
   o crescimento sumir. Corrigido: o conjunto é calculado uma vez, a
   partir do ano principal, e reaproveitado nos dois períodos.
2. `ordenar_por` rejeitava campos como `diferenca_faturamento_realizado`
   — eles só existem quando `comparar_com` é usado (são criados na hora,
   não vêm do catálogo), e a validação não sabia disso.

**O que ficou pra trás, de propósito:** a ferramenta antiga separava
"cresceu mas sem meta cadastrada" numa lista à parte, pra não confundir
com "cresceu mas abaixo da meta". A versão nova simplesmente não inclui
esses itens no resultado (não tem como pedir "os dois juntos" ainda) — um
caso de uso bem específico que a IA já era instruída a só mencionar se
perguntada diretamente.

Com isso, `metas_tools.py` e `metas_queries.py` ficaram **inteiramente
órfãos** e foram apagados — `metas_data.py` continua (o catálogo usa
`resolver_codigos_supervisor` direto de lá).

## NPS no motor genérico

Era o último indicador com ferramentas próprias (`consultar_indicadores_nps` e
`consultar_evolucao_nps`, com `queries.py` de ~1.000 linhas e uma consulta
SQL por filial por mês). Agora:
- `src/nps_data.py` carrega a tabela inteira de uma vez (1,4 s, ~85 mil
  linhas, uma por resposta) com colunas de promotor/neutro/detrator; guarda
  a leitura por 5 minutos (o dado é "ao vivo" e uma comparação de períodos
  carregaria duas vezes). Filial tem resolvedor próprio: os nomes do NPS
  diferem dos outros (`FERROLESTE INOX & ALUMÍNIO` × `FERROLESTE INOX E
  ALUMINI`).
- No catálogo, o indicador soma respostas/promotores/neutros/detratores e o
  NPS e os percentuais são fórmulas em cima das SOMAS (nunca média de NPS).
- Validado contra as ferramentas antigas em 11 combinações reais (empresa,
  filial, período, ranking por filial, por ano, mês a mês com variação,
  dois anos, evolução entre anos) antes de apagá-las — todas batendo — e
  depois conferido de forma independente, direto do banco.
- Apagados: `queries.py`, `nps_tools.py`, seus testes e o script de
  exploração que só chamava essas funções (~1.700 linhas), mais o código
  do `app.py` que só existia pros formatos de resultado do NPS antigo e as
  configurações de tabela das ferramentas já removidas (~100 linhas).

**Mudanças genéricas no motor que o NPS exigiu** (valem pra todos os
indicadores):
- As fórmulas derivadas (NPS, % de atingimento) passaram a ser calculadas
  em cada período ANTES de comparar — então `comparar_com`, `ordenar_por`
  e a variação mês a mês funcionam também sobre campos calculados
  (`diferenca_nps`, etc.).
- `comparar_com: "personalizado"` + `comparar_com_personalizado`: comparar
  com qualquer período (ex: 2023 × 2025), não só o ano anterior.
- Períodos por data ganharam `mes_anterior` e `mesmo_mes_ano_anterior`, e
  `periodo_personalizado` aceita `meses`/`anos` também nesses indicadores.
  Um período que geraria filtro numa dimensão que o indicador não tem agora
  dá erro claro, em vez de ser ignorado em silêncio.
- `variacao_utils.calcular_diferenca_percentual`: com o valor anterior zero
  (ex: NPS que foi de 0 a 75) a diferença agora existe (só o percentual fica
  vazio); antes as duas sumiam e a filial era descartada do ranking.
- Contagens (notas, respostas) continuam inteiras no resultado ("534" em
  vez de "534.0").
- A tabela do `app.py` ganhou automaticamente as colunas de comparação
  (anterior, diferença, variação) do campo principal de cada indicador — a
  antiga tabela de "evolução de NPS" e a de "cresceram mas abaixo da meta"
  mostravam isso e tinham ficado só com o valor atual.

**Achados testando o NPS na tela (você mandou as conversas):**
- Bug antigo do motor, que o NPS expôs: a variação mês a mês (e a
  necessidade diária da meta) só olhavam os `filtros` da consulta; quando o
  mês/ano vinha por `periodo`/`periodo_personalizado` (ex: "primeiro
  semestre de 2024 e 2025", ou "mês atual"), a variação sumia em silêncio.
  Agora existe um único lugar que calcula os "filtros efetivos" (filtros +
  período resolvido) e as três coisas usam ele. Coberto por teste.
- NPS de amostra pequena: "maior piora" deu Guajaras Logística 100 → 62,80,
  mas o 100 de 2024 vinha de 12 respostas (contra 250 em 2025); o "NPS de
  hoje" era 100,00 com 12 respostas. A conta está certa, mas enganosa sem o
  tamanho da amostra. Regra nova no prompt de resposta (`ai_service.py`):
  com menos de 30 respostas a IA cita a quantidade ("com base em apenas 12
  respostas"), e em comparação avisa se o período de comparação é frágil;
  com 30 ou mais não menciona. A coluna "Respostas" passou a aparecer
  sempre nas tabelas de NPS.

## Só as 18 lojas da planilha: uma lista única de filiais (`src/filiais.py`)

O chatbot responde **somente** sobre as lojas da planilha `Filiais.xlsx`
(18 lojas; a planilha tem 19 linhas porque a loja 30, ARAGUAINAV, é somada à
ARAGUAÍNA, 24). Ficam de fora: FN Atacado, Telanorte, Esquadria, os CDs, o
depósito, a administração e as 3 filiais "Logística" do NPS.

- `src/filiais.py` guarda a lista (código → nome, estado) e é a única fonte.
  Todo carregador (`carregar_faturamento_8280`, `_carregar_csv_8302`,
  `carregar_meta_tonelada`, `carregar_avaliacoes_nps`) passa o resultado por
  `padronizar_filiais`, que descarta as outras lojas e grava `FILIAL` (nome da
  planilha, ex: "TIMON"), `CODFILIAL` e `ESTADO`. Nenhum indicador, ranking ou
  total enxerga as demais.
- O código de cada base vem de onde já existia: `CODFILIAL` (faturamento,
  meta), o "-F09-" dentro do nome (meta de tonelada) e
  `dbo.Filiais.IdFilialFerronorte` (NPS). Como as quatro bases passam a ter o
  mesmo nome e o mesmo código, cruzar indicadores por filial vira um
  casamento exato, sem comparar nomes.
- Um único resolvedor de nome (`resolver_nome_filial`, com correspondência
  aproximada) substituiu os quatro que existiam (faturamento, diário, meta
  de tonelada, NPS), e `listar_filiais` lista as 18.
- **Pergunta por código de filial** ("filial 9", "codfilial 30") funciona: o
  resolvedor aceita nome ou código, e o código 30 responde como ARAGUAÍNA
  (24 + 30 somados). Pra IA não adivinhar o código pelo nome (ela trocou
  Guajajaras e Areinha num teste), toda consulta agrupada por filial devolve
  `codigo_filial` em cada linha, e o prompt de resposta tem uma regra: só
  citar código que veio no resultado e mostrar "ARAGUAÍNA (códigos 24 e 30
  somados)" quando perguntarem por qualquer um dos dois.
- Nova dimensão **`estado`** (PI, MA, TO, BA, PA) em todos os indicadores,
  aceita por sigla ou por nome (`resolver_estado`): "faturamento do Maranhão",
  "NPS do Piauí × Maranhão".
- Efeito nos números: o "total da empresa" agora é o total das 18 lojas (em
  2025, 11,6% do faturamento líquido — sobretudo o FN Atacado — ficou de
  fora). Conferido contra o CSV e o banco: Araguaína 2025 = 24 + 30, total das
  lojas, estado MA, meta de Araguaína e NPS de Timon batem ao centavo.

## Cruzamento de indicadores (`cruzar_com`)

Perguntas que combinam indicadores ("qual filial teve o maior NPS **e**
bateu a meta") viram **uma consulta só**: `{"indicador": "nps",
"cruzar_com": ["meta"], "agrupar_por": ["filial"], "filtros_calculados":
[...], "ordenar_por": {...}}`.

Como funciona (`orquestrador.py`, `_consultar_indicadores`):
1. Cada indicador é consultado separado, com os mesmos filtros e período
   (o período é traduzido pra cada um: o NPS é diário, a meta é mensal) e
   com as próprias fórmulas (NPS, % de atingimento).
2. Os resultados são juntados pela chave do agrupamento (filial, estado,
   mês, ano) — casamento exato, porque as quatro bases têm o mesmo nome e
   código de filial (ver "Só as 18 lojas"). Quem existe só num lado (ex:
   Marituba, sem NPS; novembro, sem respostas) fica com os campos do outro
   indicador vazios (`None`), e o resultado sai ordenado pela chave.
3. Depois da junção tudo que já existia funciona sobre a tabela junta, sem
   código novo: `filtros_calculados`, `ordenar_por` (com campos de qualquer
   um dos indicadores) e `comparar_com`. A tabela usa as colunas do
   catálogo (`exibicao`) dos dois indicadores — nenhum formato novo.

Proteções (erro claro em vez de resposta errada em silêncio): cruza
agrupando por filial/estado/mês/ano; por **RCA ou supervisor só quando todos
os indicadores da consulta identificam do mesmo jeito** (mesma coluna e mesmo
resolvedor — `_mesma_identificacao`): faturamento, meta e desconto usam o
código (`COD_RCA`) e cruzam por RCA; meta e desconto cruzam por supervisor; a
meta de tonelada usa o nome do RCA e não cruza por RCA com eles (a junção
sairia vazia). Dimensão pedida em `colunas` (ex: "rca") é descartada em vez
de derrubar a consulta — ela já sai sempre na tabela. Indicadores com campo de mesmo nome
(`faturamento` e `faturamento_diario`) são recusados; um filtro que um dos
indicadores não tem é erro, não é ignorado; indicador repetido ou
inexistente é erro.

**Fórmulas que dependem de dois indicadores** ficam em `catalogo.CRUZAMENTOS`
(uma entrada por par de indicadores, com os derivados e o `exibicao` da
tabela). O orquestrador as calcula depois da junção, só quando a consulta
cruza todos os indicadores do par. Hoje há uma: **faturamento × meta de
tonelada** gera `percentual_atingimento_tonelada` (toneladas vendidas ÷ meta
de tonelada da filial, reaproveitando `calcular_atingimento_meta`) e
`falta_para_meta_tonelada`. É o que responde "quais filiais bateram a meta de
tonelada" — antes a IA recusava e ainda dava um motivo errado (dizia que não
havia toneladas realizadas, mas o faturamento tem). A descrição desses campos
vai pra IA automaticamente (`gerar_descricao_cruzamentos`). Uma fórmula nova
entre dois indicadores é uma entrada nessa lista, não código novo.
`calcular_atingimento_meta` passou a devolver `None` quando o realizado é
vazio (no cruzamento um dos lados pode faltar).

Limite conhecido: a variação mês a mês e a necessidade diária (que são do
indicador principal) não entram em consulta cruzada; `comparar_com` entra.

Validação: NPS × meta por filial em 2025 confere com as duas consultas
separadas (18 filiais) e com a junção refeita em pandas a partir do CSV;
"top 3 NPS entre quem bateu a meta" confere com o filtro manual; o
atingimento de tonelada (2024: 16 filiais, 2025: 18) confere com a conta feita
direto dos CSVs, inclusive a lista e a ordem de quem bateu a meta; 17 testes
em `tests/test_cruzamento.py`.

## Tabela da tela: uma regra só, sem formato por pergunta

Antes, `preparar_tabela` (app.py) tinha três "pivôs" de casos especiais
(filial × 2 anos, 2 períodos, uma métrica por mês) e mostrava todas as colunas
marcadas "sempre" no catálogo — por isso "NPS e atingimento" saía com Meta,
Faturamento, Respostas etc. Agora:

1. **Colunas:** a IA informa `colunas` na consulta (só o que a pergunta pediu,
   ex: `["nps", "percentual_atingimento"]`). O motor valida os nomes contra o
   catálogo e devolve `tabela`: as linhas recortadas em identificação + essas
   colunas + a comparação delas (anterior/diferença/variação). O resultado
   completo continua indo pra IA (que precisa, por exemplo, do nº de respostas
   pra avisar de amostra pequena); a `tabela` é removida antes de chegar nela
   (`chatbot.py`). As linhas levam `_colunas_pedidas` pra tela saber que a
   escolha já foi feita. Sem `colunas`, vale o padrão do catálogo (`sempre` ou
   palavra na resposta) — nada quebra. "Respostas" e "Meta Tonelada (RCA)"
   deixaram de ser "sempre".
2. **Formatação pelo tipo:** moeda, percentual e, novo, números em português
   ("96,28"; contagens sem casa decimal, "1.058" — antes saíam "96.28" e
   "1058.0"); vazio = "sem dados".
3. **Layout (`_pivotar`), a mesma regra pra qualquer indicador:** quando sobram
   duas ou mais dimensões que variam, a de MENOS valores distintos vira colunas
   (empate: a de tempo) e o resto fica nas linhas. 2 filiais × 6 meses:
   `Mês | LOURIVAL | LOURIVAL — Variação (mês anterior) | TIMON | ...`; filiais ×
   2 anos: `Filial | 2024 | 2025 | 2025 — Variação (ano anterior)`. As colunas
   ficam agrupadas por **métrica**: o valor dos itens comparados sempre lado a
   lado (`LOURIVAL — NPS | SANTA INÊS — NPS`), depois Respostas, depois a
   variação — antes ficavam agrupadas por filial e o NPS de uma ficava longe do
   da outra. Coluna toda vazia some (a variação do primeiro ano). Passando de 12 colunas, ou com só uma
   dimensão que varia, a tabela fica comprida (uma linha por combinação).
   Comparação com `comparar_com` já é larga (`NPS | NPS (anterior) | Diferença |
   Variação`) e não precisa de pivô.
4. **Variação entre anos:** o motor passou a calcular `percentual_ano_anterior`
   também quando o agrupamento tem `ano` sem `mes` (antes só com mês; quem
   fazia isso era o pivô "Filial × 2 anos" do app.py, agora removido).

O `app.py` ficou ~140 linhas menor (3 pivôs, `_montar_tabela_comparacao_dois_anos`
e `ocultar_repeticoes_consecutivas`, que ninguém chamava, saíram).

## Comparar dois itens entre si (`comparar_filtros`)

"Compare o NPS de Lourival e Santa Inês mês a mês" é uma comparação **entre as
duas filiais** em cada mês — não a evolução de cada uma no tempo (o que o
chatbot fazia antes: agrupava por filial e mês e mostrava a variação mês a mês
de cada uma). A consulta agora é:
`{"indicador": "nps", "filtros": {"filial": ["Lourival"], "ano": [2025]},
"comparar_filtros": {"filial": ["Santa Inês"]}, "agrupar_por": ["mes"]}`.

Reaproveita o `comparar_com` (que compara dois PERÍODOS): o motor roda a
consulta de novo com os filtros de `comparar_filtros` no lugar e junta linha a
linha pela chave que sobrou (o mês), com o mesmo cálculo de diferença e
percentual (`_combinar_comparacao`). O 1º item citado é o valor ("A"), o 2º é o
`_anterior` ("B"), a diferença é A − B. O resultado traz `comparacao_entre` (os
nomes dos dois lados e "como_ler", pra IA não confundir "anterior" com tempo) e
a tabela recebe `_rotulos`, que trocam os títulos das colunas pelos nomes:
`Mês | LOURIVAL | SANTA INÊS | Diferença (LOURIVAL − SANTA INÊS) | Diferença %`.

Funciona pra qualquer indicador e dimensão (filial × filial, estado × estado,
RCA × RCA), mês a mês, ano a ano ou sem agrupar (total do período). Um mês em
que só um dos lados tem dado não some (o outro lado fica "sem dados") e o
resultado sai ordenado. Não calcula a variação mês a mês de cada item.
Regras: só dois itens de cada vez (3 ou mais: `agrupar_por` e a tabela lado a
lado, sem diferença); a dimensão comparada não pode estar em `agrupar_por`; sem
`colunas`, a tabela usa o campo principal. Se a IA mandar `comparar_com` (período
contra período) e `comparar_filtros` juntos — ex: "Timon e Lourival, 1º semestre de
2025 contra o de 2024" —, o motor lê como cada item, período contra período
(`_normalizar_comparacoes`: junta os itens nos filtros, agrupa pela dimensão e fica
só com `comparar_com`), em vez de devolver erro ao usuário.

## Investigação: ligar o faturamento no Oracle (WinThor) em vez do CSV

O faturamento (mensal e diário) hoje vem de CSVs exportados das rotinas 8280/
8302 e param em dezembro de 2025 — sem nenhum dado de 2026, e sem atualizar
sem exportação manual. A ideia é o motor consultar o Oracle de produção
direto (schema `FNORTE`, banco `WINT`), sempre só leitura. A conexão já
existe (`src/connection.py`, credenciais no `.env`) e foi testada: funciona.

**Método:** como não existe o texto das rotinas 8280/8302, a regra foi
descoberta por comparação — uma consulta no Oracle, comparada campo a campo
com o CSV (o gabarito, seis anos de dados) até bater exatamente. Feito pra
Timon, janeiro/2025, vendedor por vendedor, e depois validado nos 6 anos
inteiros e nas 18 lojas de uma vez, só leitura, nada alterado.

### Primeira tentativa (`PCMOV`, item de venda) — abandonada

`PCMOV` é a tabela de itens de venda (uma linha por produto vendido). Um
teste de um mês só (Timon, jan/2025) bateu exato: venda bruta = soma de
`ROUND(QT * PUNIT, 2)` com `CODOPER='S'` e `DTCANCEL IS NULL`; valor de
tabela = mesma conta com `PTABELA`; devolução = mesma conta com
`CODOPER='ED'`. Mas validando os **6 anos inteiros**, apareceu uma
divergência grande (às vezes o dobro do valor certo): a `PCMOV` guarda, pra
muitas vendas, **duas linhas pra mesma venda** — uma com `ESPECIE='NF'`
(nota fiscal real, ligando com `PCNFSAID`) e outra com `ESPECIE='CN'`, sem
número de nota real (`NUMNOTA = NUMTRANSVENDA`, o próprio código interno).
Não é raro: 25% a 29% de todas as vendas, todo ano, de 2020 a 2025 — e
crescendo. Consultado o supervisor: **faturamento não deve ser calculado
pela `PCMOV`** — existe fonte própria pra isso (abaixo).

### Fonte certa: `GFN_MVIEW_VENDAS_HIST` + `GFN_MVIEW_VENDAS_ANO_ATUAL`

Views (85 colunas) já preparadas pra vendas, com `ESPECIE` direto (sem
precisar de join) — `HIST` cobre 2009 até 31/12/2025, `ANO_ATUAL` cobre o
ano corrente (2026 em diante); juntas, cobrem o período todo. Validado nos 6
anos, nas 18 lojas, filial+ano+mês+vendedor: **venda bruta e valor de
tabela bateram exatos (diferença 0,00) em 10.425 das 10.435 combinações** —
sem precisar filtrar `ESPECIE`, a view já resolve a duplicação da `PCMOV`
sozinha. As 10 linhas com diferença são pequenas (maior: R$ 67 mil, numa
filial que fatura dezenas de milhões); as ~590 linhas "só no CSV" são RCA
com venda R$ 0,00 (a view não cria linha pra quem não vendeu nada — não é
perda de dado).

**Devolução (`GFN_MVIEW_DEV_HIST`/`GFN_MVIEW_DEV_ANO_ATUAL`, 103 colunas,
campo `VLDEVOLUCAO`, data `DTENT`):** achado um problema parecido, mas bem
menor. Em 53 de 5.485 combinações o valor não bateu — o pior caso
(Imperatriz, vendedor 8436, jul/2025) deu quase o dobro (R$ 444.891,77
contra R$ 225.045,63 do CSV). Investigando: duas devoluções diferentes,
ligadas a **duas notas de venda diferentes e reais** (não é o mesmo padrão
"nota falsa" da `PCMOV`), com os mesmos produtos/quantidades/valores — indício
de duplicação, causa não confirmada. **Medido o impacto real:** a
diferença total (R$ 1,54 milhão) é 0,031% da venda bruta total (R$ 4,89
bilhões) e 2,37% do total de devolução (que já é só 1,33% da venda bruta).
**Decisão tomada:** aceitar essa margem pequena (mesmo espírito da decisão
sobre o peso, abaixo), sem investigar mais.

### Peso líquido (toneladas): dois problemas achados, um corrigido

**1. Bug real no próprio WinThor, corrigido (`scripts/atualizar_faturamento_oracle.py`,
`_PESO_POR_LINHA`):** a princípio a validação de peso deu erro grande (3,17%
no ano de 2025 inteiro, com casos extremos de até +1.387% num vendedor/mês)
— bem maior que uma simples margem de arredondamento. Investigando o pior
caso (uma chapa de aço grossa, filial 7): o produto tem `PESOLIQ` cadastrado
de 456,5 kg (o peso de **uma chapa inteira**), mas a venda foi de 456,51
**quilos** (não "456,51 chapas") — como a unidade do produto é `KG`, a
quantidade vendida (`QTVENDA`) já É o peso. A conta padrão
(`QTVENDA × PESOLIQ`) multiplica o peso por ele mesmo, dando 208 toneladas
pra uma venda de R$ 3.807. Confirmado que **não é erro da view nem meu**: o
próprio cabeçalho oficial da nota (`PCNFSAID.TOTPESOLIQ`) já tem esse mesmo
valor inflado — o bug existe no WinThor. **Correção:** quando
`UNIDADE = 'KG'`, o peso da linha é a própria `QTVENDA`; só multiplica por
`PESOLIQ` quando o produto é vendido por peça. Isso derrubou o erro de
3,17% pra **1,18%** no ano de 2025 (18 lojas) — só 13 de 367 vendedores
ficaram com diferença acima de 20% no ano, contra a maioria antes.

**2. O que sobra (~1,18%), não vou resolver — margem pequena aceita:** a
conta `QTVENDA × PESOLIQ` (produtos vendidos por peça) bate quase perfeito
pra vendas de **2026** (testado contra `GFN_MVIEW_VENDAS_ANO_ATUAL`, Timon
jan/2026: 1.137.231,15 contra 1.137.231,70 da view — diferença de 0,55 em
mais de 1 milhão), mas erra um pouco pra **2025 pra trás**, porque o peso
cadastrado do produto é o de **hoje**, e o WinThor não guarda o peso como
ele estava na data da venda (confirmado por um colega de TI: "essa parte
não é padronizada") — não é uma tabela que falta achar, a informação exata
não existe mais. **Decisão tomada:** aceitar essa margem (pequena, só em
anos anteriores — vendas do ano corrente batem quase exato), e avisar isso
na resposta da IA quando a pergunta for sobre toneladas/peso de anos
passados.

**Meta e nomes: também bateram exatos.** `PCMETARCA` guarda a meta **por dia**
(uma linha por vendedor por dia, campo `VLVENDAPREV`) — a soma do mês, por
vendedor, bate ao centavo com `VALOR_META` do CSV (conferido nos 5 vendedores
de Timon jan/2025, diferença 0,00 em todos). Nome do vendedor vem de
`PCUSUARI.NOME`, nome do supervisor de `PCSUPERV.NOME` (join por
`CODSUPERVISOR`) — mesmos nomes que o CSV já usa. As duas
`GFN_MVIEW_VENDAS_*` já trazem `CODSUPERVISOR`/`SUPERV` (nome) direto,
sem precisar desse join, se for usar a mesma consulta pra tudo.

### Como a troca será feita: script agendado, não consulta ao vivo

Decisão do supervisor (mesmo padrão de código que ele já usa em outros
projetos, com `oracledb` + `get_connection` de `src/connection.py`): em vez
do motor genérico consultar o Oracle a cada pergunta (o plano original, com
cache curto tipo NPS), um **script separado** consulta o Oracle
periodicamente e **regrava o CSV** — o motor continua lendo CSV exatamente
como hoje, sem nenhuma mudança nele. Só o *que escreve* o CSV muda: de
exportação manual pra automática. Menos risco (a parte "quente" do sistema
nem muda) e menos carga no banco de produção (consultado só 1x por período,
não por pergunta). Falta decidir: frequência de atualização (diária?) e
como disparar o script (Agendador de Tarefas do Windows?) — combinado de
deixar pra depois.

**Script escrito e validado:** `scripts/atualizar_faturamento_oracle.py`.
Consulta vendas (`GFN_MVIEW_VENDAS_HIST`/`_ANO_ATUAL`), devolução
(`GFN_MVIEW_DEV_HIST`/`_ANO_ATUAL`) e meta (`PCMETARCA`) — três consultas
simples, já agregadas no banco — e junta em Python por
filial/ano/mês/vendedor; grava no mesmo formato (`;`, latin1, decimal `,`)
que `carregar_faturamento_8280` já lê, com só as colunas de fato usadas em
`src/*.py` (nenhuma coluna morta tipo `PERC_META`/`VALOR_CANC`/etc., que o
CSV manual tem mas nada no código lê). Roda com `python -m
scripts.atualizar_faturamento_oracle [--ano-inicio AAAA] [--saida
caminho.csv]`; sem argumentos, sobrescreve o CSV atual — testado sempre
com `--saida` apontando pra um arquivo separado, nunca sobrescrevendo o
CSV real, até aqui.

**Validado nos 6 anos inteiros (2020-2025), 18 lojas** (não só 2025):
venda bruta e meta batem exatos em todo ano (0,000%, exceto 2025 com
0,010%); venda líquida com diferença insignificante (-0,00% a -0,06%, a
margem da devolução já aceita); peso entre +0,71% e +1,15% em todo ano —
sem nenhum ano fugindo do padrão, confirmando que a correção do peso
(abaixo) generaliza bem, não é um acerto isolado de 2025.

**Dois bugs reais achados e corrigidos escrevendo esse script** (nenhum
tinha aparecido nos testes manuais anteriores, mais restritos):
1. `SELECT *` dentro de um `UNION ALL` de duas views — o Oracle junta as
   colunas por posição, não por nome; corrigido nomeando as colunas
   explicitamente dos dois lados do `UNION ALL` (`_COLUNAS_VENDA`,
   `_COLUNAS_DEV`).
2. `TO_DATE(:ano, 'YYYY')` **não** vira 1º de janeiro daquele ano — o
   Oracle completa o mês/dia que faltam no formato com o mês/dia de
   **hoje** (não com 01/01), então o filtro "desde 2025" virou "desde
   setembro de 2025" e apagou 8 meses em silêncio, sem erro nenhum.
   Corrigido passando uma data real do Python (`date(ano, 1, 1)`) como
   parâmetro, em vez de montar a data dentro do SQL.

**Ainda faltando pra fechar o faturamento** (não investigado ainda): o
faturamento diário com forma de pagamento (rotina 8302) — provavelmente a
mesma dupla `GFN_MVIEW_VENDAS_HIST`/`_ANO_ATUAL` com granularidade de dia em
vez de mês, e a forma de pagamento (`CODCOB`, presente nessas views).

## O que continua sem fonte, e por quê

| Indicador | Situação |
|---|---|
| `inadimplencia`, `clientes` | Registrados no catálogo (documentando o que o sistema deveria ter), mas sem nenhuma fonte de dado real conectada ainda. |

## Desconto (conectado em 01/10/2026)

- **Fonte:** o mesmo `faturamento_mensal.csv` (mesma consulta de vendas):
  `VENDA_TABELA` (`SUM(VLTABELA)`, coluna nova) e `VALORDESC`, que passou a
  ser `SUM(VLDESCONTO * QT)` — antes era "venda − tabela" (a conta do
  `VALORDESC` da 8280, negativa). Agora o desconto é a mesma conta em todo o
  chatbot: indicador desconto, campo "Desconto" do faturamento mensal e do
  diário. Sem consulta nova ao banco.
- **Fórmula:** % Desconto = desconto concedido ÷ faturamento de tabela,
  calculado sobre as somas (`motor_metricas.calcular_desconto`).
- **Por que `VLDESCONTO * QT`:** em `VIEW_VENDAS_RESUMO_FATURAMENTO` o
  `VLDESCONTO` vem de `PCMOV` e é **por unidade** (preço de tabela − preço
  vendido; zero quando o item sai na tabela ou acima). Conferido em ago/2026:
  em 100% dos 73.483 itens com desconto, `VLDESCONTO × QT` = `VLTABELA −
  VLVENDA`, e nenhum item com `VLDESCONTO` = 0 foi vendido abaixo da tabela.
  O `PERCDESC` da rotina 8280 soma sem multiplicar (dá 0,05% em ago/2026, errado);
  multiplicado, bate centavo a centavo com a rotina 8302 (R$ 2.259.420,82,
  que usa `GFN_MVIEW_VENDAS_ATUAL`, onde o campo já vem total).
- **Venda acima da tabela conta zero** (não abate o desconto dos outros
  itens), igual à 8302. A conta "tabela − vendido" (usada no `VALORDESC` da
  8280 e, até 01/10/2026, no campo "Desconto" do faturamento mensal) abate, e por isso
  dá menos (1,56% x 2,20% em ago/2026) e fica negativa em filiais que vendem
  acima da tabela (FN Atacado).
- **Devolução não entra**, como nas duas rotinas do WinThor.
- Dimensões: filial, estado, RCA, supervisor, mês, ano. Validado: Timon
  ago/2026 = R$ 310.567,19 / R$ 9.920.150,98, igual ao banco.

### Desconto por cliente (02/10/2026)

- **Fonte:** `src/cliente_data.py` gera dois CSVs (cache de 1h, igual aos
  outros, desde 2020), lidos SÓ quando a pergunta pede cliente/empresa
  (`fontes_por_dimensao` no catálogo — a mesma regra que antes era só da
  forma de pagamento):
  - `desconto_cliente.csv` (~1,15 milhão de linhas, 43 MB): desconto e
    faturamento de tabela por filial/ano/mês/RCA/supervisor/cliente — só
    códigos e números. Desconto com 4 casas (com 2, o arredondamento por
    linha somava até R$ 10/ano de diferença).
  - `clientes.csv` (~192 mil): cadastro (`PCCLIENT`) de quem comprou desde
    2020 — nome, fantasia, CNPJ, cidade, empresa.
  Gerar do Oracle leva ~2,5 min; ler, ~2,3 s. Totais por ano batem com o
  `faturamento_mensal.csv` (diferença de centavos, arredondamento do mensal).
- **Empresa = início do CNPJ** (8 primeiros dígitos). Cada loja é um
  cadastro (código próprio) com o seu CNPJ; as lojas da mesma empresa só
  mudam o final (ex: as lojas Mix, Eletro, Hiper e Mateus Supermercados
  começam com 03.995.515). Sem CNPJ válido (CPF, em branco, "000…") o
  cliente fica sozinho ("CLI<código>"). Empresas diferentes do mesmo grupo
  (Mateus Supermercados x Armazém Mateus) NÃO são juntadas automaticamente.
- **Duas dimensões:** "empresa" (todas as lojas) e "cliente" (o código, UMA
  loja). Nome → empresa; se o nome acha várias empresas, a consulta para
  com a lista (a que mais compra primeiro, até 10) e a IA pergunta qual.
  Ranking de clientes = agrupar por empresa (cada uma aparece uma vez).
- **Filial = filial da Ferronorte que vendeu**, não a cidade do cliente —
  é o filtro que o controle de acesso vai usar.
- **Nome/CNPJ/cidade** vêm junto ao agrupar (`ATRIBUTOS_DIMENSAO` no
  catálogo): são identificação, nunca viram coluna no pivô da tabela.
- **Total de todas as linhas:** toda consulta agrupada simples traz
  `total_de_todas_as_linhas` (antes do limite) — a IA usa esse total em vez
  de somar a lista (ex: desconto da empresa + tabela por loja).
- **Período obrigatório no desconto** (`periodo_obrigatorio` no catálogo):
  sem período a consulta somaria desde 2020 e enganava (ex: "desconto do
  Mateus em Timon" dava R$ 205.100,63, sendo R$ 204.332 de 2020 e R$ 576 em
  2026). Agora o motor recusa e a IA pergunta o período. Nos outros
  indicadores, consulta sem período descreve "todo o histórico disponível"
  em `periodo_consultado` (antes vinha nulo e a IA omitia).
- **Respostas longas** (teste de 02/10/2026: "Mateus por loja em 2024 e
  2025" listou 149 linhas no texto, 116 com R$ 0,00, sem total): a resposta
  começa pelo total, cita só as 10 primeiras (ordenadas pelo desconto) e
  conta itens por `quantidade_por_dimensao` (95 lojas x 2 anos = 149
  linhas). `itens_filtrados` traz o nome oficial da empresa/cliente
  filtrado ("mix mateus" → "MATEUS SUPERMERCADOS S A").
- **Mesmo CPF = mesmo cliente** (02/10/2026): CPF válido também vira a
  "empresa" (o CPF inteiro). Junta 172 pessoas cadastradas mais de uma vez e
  os 5 cadastros "CONSUMIDOR FINAL" (todos com CPF 111.111.111-11 — o
  balcão sem cliente identificado), que apareciam duas vezes no ranking.
  Consumidor Final em 2026: R$ ~958 mil, uma linha só.
- **"Os N maiores e, dentro de cada um, os principais"**: `ordenar_por`
  aceita `"por"` (dimensão de `agrupar_por`) e `"limite_grupos"`. Os grupos
  são escolhidos pelo TOTAL de cada um (`totais_por_grupo`, mesmos dados
  agrupados só pela dimensão), e `limite` corta dentro de cada grupo. Antes,
  "RCAs que mais deram desconto e pra quais clientes" cortava nos 5 maiores
  PARES (RCA, cliente) e deixava de fora a Adriana Moraes, 2ª maior em
  set/2026.
  Sem `limite`, as linhas de cada grupo ficam na ordem natural (antes, "o
  histórico mês a mês dos 3 maiores RCAs" saía com os meses ordenados pelo
  valor: agosto, maio, julho…).
- **Variação mês a mês do desconto é em R$** (`campo_variacao` no catálogo):
  antes era a variação do % (Paulo Sergio, mai→jun/2026: % de 9,05 para
  9,07 = "+0,22%", enquanto o desconto caiu de R$ 115.561 para R$ 19.218,
  -83%).
- **Tabela esparsa não pivota** (`app._pivotar`): se menos da metade das
  células teria valor, a tabela fica em linhas.
- Prompt: "pedir_esclarecimento" pergunta só o que falta (sem listar os
  assuntos disponíveis); lista sem quantidade usa limite 10; erro de
  digitação provável vira "você quis dizer…?"; a lista de empresas parecidas
  é numerada, com CNPJ/"pessoa física", sem códigos internos.
- Vendas para a própria Ferronorte (cadastros "Comercial Ferronorte")
  entram, por decisão de 02/10/2026. "CONSUMIDOR FINAL" (CPF genérico) é
  um cliente só e lidera rankings por filial.

## Período sempre explícito na resposta + trava contra número inventado

- **"mês passado" saía como o mês errado:** o resultado não dizia qual
  período foi consultado e a IA que escreve a resposta deduzia (dizia
  "agosto" pra dado de setembro). Agora todo resultado traz
  `periodo_consultado` (e `periodo_comparado`) com a descrição pronta
  ("setembro de 2026") e a resposta é obrigada a usá-la. Novos períodos
  prontos: `ano_anterior` e `semana_anterior` (o código calcula a data, não a
  IA).
- **IA inventando número no "responder_com_historico":** em "e o
  percentual?", depois de mostrar só o R$, ela calculava um % com um
  faturamento que nunca apareceu. `chatbot.py` agora confere os números
  dessa resposta contra o histórico; número novo = resposta descartada e a
  pergunta é reinterpretada pra consultar (se insistir, pede pra reformular).

## Ferramentas registradas: antes x depois

- Antes da migração: 10 ferramentas.
- Hoje: **3** — `consultar_dados_comerciais`, `verificar_rca`,
  `listar_filiais`.
- Removidas por serem 100% cobertas pela ferramenta nova (confirmado com
  dado real E com a IA escolhendo a ferramenta certa, não só "deveria
  funcionar"): `consultar_indicadores_faturamento`,
  `consultar_indicadores_faturamento_diario`, `consultar_metas`,
  `consultar_meta_tonelada`, `consultar_crescimento_abaixo_meta`,
  `consultar_indicadores_nps`, `consultar_evolucao_nps`,
  `listar_rcas_filial`.
- **Mantida de propósito**: `verificar_rca` — confirma se um RCA existe
  SEM período (a ferramenta genérica sempre espera algum filtro/período
  pra buscar dado); esse contrato é diferente o suficiente pra continuar
  justificando uma ferramenta própria.

## Código morto removido (função sem ninguém chamando)

Depois de apagar as ferramentas acima, ficaram órfãs (e foram removidas):
`consultar_indicadores_faturamento` (`faturamento_queries.py`),
`executar_consulta_indicadores_faturamento` (`faturamento_tools.py`),
`consultar_indicadores_faturamento_diario` e a função auxiliar
`_rotular_periodo` (`faturamento_diario_queries.py`/`faturamento_diario_tools.py`),
`executar_consultar_metas` (`metas_tools.py`) — junto com os testes que só
cobriam essas funções. Depois, ao conectar `meta_tonelada`, os arquivos
`meta_tonelada_queries.py` e `meta_tonelada_tools.py` ficaram inteiros sem
ninguém chamando (a única coisa neles era a busca/ponte que a ferramenta
antiga usava) — **apagados por completo**, junto dos testes deles e do
seletor de coluna correspondente em `app.py`.

## Consolidação de arquivos (menos arquivos de verdade, não só menos linha)

Depois da limpeza acima, `faturamento_queries.py` e
`faturamento_diario_queries.py` não tinham mais nenhuma consulta — só uma
função de listagem de filiais cada. E `faturamento_diario_tools.py` só
tinha a resolução de nome de filial. Nenhum dos três fazia mais sentido
como arquivo próprio, então:
- A listagem e a resolução do nome da filial foram pra dentro dos
  `*_data.py` e, depois, todas substituídas pela lista única de
  `filiais.py` (ver "Só as 18 lojas").
- `faturamento_queries.py`, `faturamento_diario_queries.py` e
  `faturamento_diario_tools.py` foram **apagados**.

`faturamento_tools.py` continua existindo — é onde mora
`executar_verificar_rca`, a única função dele que ainda é uma ferramenta de
IA de verdade (`verificar_rca`).

## Prompts trimados

`src/prompts/faturamento.py` e `src/prompts/metas.py` tinham dezenas de
exemplos ensinando a IA a chamar as ferramentas apagadas — ficaram
desatualizados e são exatamente o tipo de "código a mais por indicador" que
a arquitetura nova deveria evitar. Reescrevi os dois: `faturamento.py` foi
de 563 para ~215 linhas, `metas.py` de 412 para ~180 — mantendo só as regras
de negócio que ainda não são óbvias pelo contrato novo (ex: RCA sem período,
forma de pagamento exige data_inicial/data_final, necessidade diária só no
mês atual), traduzidas pro formato de `consultar_dados_comerciais`.

## Bug real encontrado em produção e corrigido

A usuária relatou o chatbot respondendo literalmente `None` pra "qual
faturamento da filial de timon, lourival e tibiri em 2024 e 2025". Causa:
`consultar_dados_comerciais` não tinha entrada em
`CONFIG_TABELA_POR_FERRAMENTA` (app.py) — quando o resultado batia no pivô
"Filial x 2 anos", a coluna de valor vinha `None` e o pandas quebrava com
`KeyError(None)`; o tratamento de erro do app então trocava a resposta
CERTA que a IA já tinha gerado pelo texto do erro (`str(KeyError(None))` é
literalmente a string `"None"`). Corrigido em duas frentes:
1. `CONFIG_TABELA_POR_FERRAMENTA` ganhou uma entrada pra
   `consultar_dados_comerciais` — **gerada automaticamente**, não escrita à
   mão: cada indicador do `catalogo.py` ganhou um campo `"exibicao"` (tipo,
   rótulo, quando a coluna aparece), e `catalogo.gerar_colunas_tabela()`
   junta o de todos os indicadores conectados. Um indicador novo só
   preenche `"exibicao"` na entrada dele; a tabela do app.py reconhece as
   colunas sozinha.
2. O pivô "Filial x 2 anos" agora não quebra mesmo se uma ferramenta futura
   também não tiver config — cai pro formato de tabela padrão em vez de
   indexar uma coluna inexistente.
Coberto por `tests/test_app.py` (2 testes de regressão).

## Segundo bug real encontrado em produção e corrigido: IA errando "o maior" numa lista grande

A usuária pegou o chatbot respondendo "FN ATACADO" pra "quais filiais
obtiveram o melhor faturamento em 2025" — errado: Timon (R$ 112,1 mi) é
maior que FN ATACADO (R$ 107,1 mi), e isso ficou evidente porque a mesma
conversa, logo depois, mostrou os 3 maiores com Timon em primeiro. Não era
bug no motor (os dados retornados já estavam certos) — era a segunda
chamada ao Gemini (a que escreve a resposta final) "olhando" uma lista de
23 filiais pra achar o maior, e errando. Isso já existia nas ferramentas
antigas (mesmo padrão: devolvia a lista inteira e confiava na IA pra
comparar), só ficou visível agora.

Corrigido adicionando `ordenar_por` (`{"campo", "ordem", "limite"}`) ao
motor genérico — `orquestrador._aplicar_ordenacao()` ordena e corta pros N
primeiros em Python, de forma exata, igual ao restante do motor. Os
prompts (`faturamento.py`, `metas.py`) e a descrição da ferramenta em
`tool_manager.py` foram atualizados pra a IA pedir `ordenar_por` em vez de
tentar comparar a lista "de olho". Testado com as mesmas perguntas que
erraram antes — todas corretas agora, incluindo a que tinha errado.

## O que falta (gaps conhecidos, não é feature futura vaga)

1. **6 testes antigos de `tests/test_chatbot.py`** seguem falhando: esperam
   que `processar_pergunta` devolva só o texto, mas ela devolve
   `(texto, tabela, ferramenta)` desde o botão de tabela, e dois ainda usam
   nomes de ferramentas apagadas. É teste desatualizado, não bug do chatbot.

## Testes

`tests/test_motor_metricas.py`, `tests/test_orquestrador.py` (motor
genérico) e `tests/test_app.py` (regressão da tabela) — testes novos, todos
passando (mais `test_nps_data.py` e `test_variacao_utils.py`). Suíte
completa: 193 passando, 6 falhando (as do `test_chatbot.py`, ver "o que
falta" — já existiam antes da migração). As 3 falhas antigas de NPS foram
consertadas antes de migrar o NPS (testes que ainda usavam `ano=` em vez de
`anos=[...]`). O total de testes oscila porque os das funções mortas são
removidos junto com elas — não é perda de cobertura.

## Correções do teste de faturamento (05/10/2026)

- **"Dia de menor faturamento de Timon em ago/2025"** respondeu "31/08/2025,
  R$ 10.133.670,17" — era o TOTAL do mês (a IA não agrupou por dia) com a
  data final do período. Certo: 02/08/2025, R$ 64.485,37. Regras novas: dia/mês
  de maior/menor = agrupar por dia/mês + ordenar com limite 1; a resposta só
  cita uma data que veio no resultado.
- **Comparação com um lado sem venda** (10/08/2025, domingo, x 20/08/2025)
  descartava tudo ("não há faturamento"). Agora o período principal vazio
  entra com os campos nulos e o outro lado aparece (R$ 257.846,53).
  "Compare os dias 10 e 20" = dois dias soltos, nunca o intervalo 10→20.
- **Agrupado por 2+ anos com `comparar_com`**: cada ano era comparado com ele
  mesmo (2024 x 2024 = +0,00%). O `comparar_com` é descartado — a variação ano
  a ano já vem de `_aplicar_variacao_temporal`.
- **Supervisor sem nome** ("supervisor com código 9"): `ATRIBUTOS_DIMENSAO`
  ganhou "supervisor" → `supervisor_nome` (`NOME_SUPERVISOR`). Atributo só entra
  se a coluna existir na base (o arquivo de cliente não tem o nome do supervisor).
- **Desconto por dia/semana** ("qual RCA mais concedeu desconto semana
  passada?" era recusado: o indicador desconto é mensal). Novo indicador
  `desconto_diario` (filial, estado, RCA, dia), lendo o `faturamento_diario.csv`
  — que passou a ter `VENDA_TABELA` (`SUM(VLTABELA)`) e o desconto com 4 casas.
  Fonte `GFN_MVIEW_VENDAS_ATUAL` (a da 8302): Timon ago/2026 = R$ 310.567,19 /
  R$ 9.920.150,98, idêntico ao indicador mensal. Sem supervisor e cliente.
- **Meta igual à rotina 8139** (05/10/2026): o `faturamento_mensal.csv` era
  montado a partir das VENDAS (merge "left"), então a meta de código sem
  venda no mês sumia — quase sempre contas da empresa que guardam parte da
  meta da filial (ex: "COMERCIAL FERRONORTE LTDA-F09-TIMON", R$ 466 mil em
  set/2026). Faltavam R$ 67 mi (7,4%) em jan-out/2026 (Maiobão -29,5%). Agora
  a meta entra com "outer" (venda zero, supervisor do cadastro `PCUSUARI`):
  jan-out/2026 = R$ 905.598.248, igual à 8139. Meta de mês futuro fica fora.
- **Contas da empresa** (nome com COMERCIAL FERRONORTE, FERRONORTE COM DE
  FERRAGENS, FERROLESTE ou METALURGICA FERRONORTE): coluna `CONTA_EMPRESA`.
  Entram na meta/faturamento da filial, mas saem das listas de RCA
  (`_rcas_com_meta_cadastrada`). Pedidas pelo nome/código, respondem.
  Inclui o código 1 ("COMERCIAL FERRONORTE LTDA-F01-MATRIZ").
- **Mês em andamento fora do acumulado do ano** (`acumulado_so_meses_fechados`
  em meta e meta_tonelada; `orquestrador._separar_mes_em_andamento`): em
  05/10/2026, "atingimento de 2026" somava a meta de outubro inteira contra 5
  dias de venda (Timon 97,0% → 86,1%; Parnaíba, que bateu a meta até setembro,
  aparecia com 91%). Agora, pro ano corrente sozinho (sem mês pedido, sem
  agrupar por mês, sem comparação), o resultado é de janeiro ao mês anterior e
  o mês em andamento vem em `mes_em_andamento` (mesmos itens do resultado), que
  a resposta cita à parte. Vale também quando a meta está cruzada com outro
  indicador. Decisão provisória até o supervisor responder.
- **"Quem MENOS deu desconto"** (`menor_ignora` em desconto e
  desconto_diario; `orquestrador._separar_sem_valor`): em ordem crescente,
  quem tem desconto abaixo de R$ 1,00 sai da lista e vem em `fora_da_lista_de_menor`
  (quantos e quais). Abaixo de R$ 1,00 é arredondamento: item vendido em
  kg/metro dá meio centavo (21,9 kg x R$ 10,35 = R$ 226,665 → R$ 226,67 na
  tabela, R$ 226,66 na nota → "desconto" de R$ 0,005). Só muda a lista; os
  totais somam tudo, iguais à 8302. "Menos desconto" ordena pelo % (R$ só se
  a pergunta pedir valor). Ex 02/10/2026: 7 RCAs sem desconto; menor de
  verdade Dalva F05, R$ 17,89 (0,02%).
- **Total de lista de RCAs ≠ total da filial**: ao agrupar por RCA (só
  vendedores com meta), `total_de_todas_as_linhas` ganha uma `observacao`
  pra IA não apresentá-lo como total da filial/empresa do WinThor.
- **Dia da semana relativo** ("sexta da semana passada"): a IA não sabia a
  data e consultava a semana inteira, respondendo como se fosse a sexta.
  `ai_service.calendario_recente()` vai nos dois prompts com a data de cada
  dia desta semana e da passada (segunda a domingo); a resposta não pode
  citar período diferente de `periodo_consultado`.
- **% de desconto com 4 casas** (`motor_metricas.calcular_desconto`): com 2,
  quem quase não teve desconto empatava em 0,00% e a ordem de "menos
  desconto" ficava aleatória. A tela mostra "menos de 0,01%" abaixo disso.

## Atualização dos CSVs em segundo plano (06/10/2026)

- **Antes:** o 1º a perguntar depois de 1 hora esperava o Oracle (06/10/2026:
  ~5 min — diário e mensal regerados um depois do outro na mesma pergunta).
- **Agora:** `src/atualizador.py` (iniciado pelo `app.py`, só quando roda no
  Streamlit) atualiza em segundo plano: COMPLETA ao abrir e no 1º ciclo de cada
  dia (a partir das 7h); PARCIAL (mês atual + anterior, juntando com o
  histórico do CSV) de hora em hora das 7h às 19h; nada à noite. Medido:
  parcial das 4 bases = 98 s (mensal 20 s, diário 10 s, forma de pagamento
  13 s, cliente 54 s) contra ~6-7 min da completa; o pico de ~500 MB do
  cliente some na parcial. Parcial x completa: idênticas em todos os meses
  fechados (só o dia/mês corrente difere, por vendas novas entre as duas).
- `src/arquivos_oracle.py` reúne o que antes era copiado em 4 módulos
  (tentativas no Oracle, gravação, leitura): grava num `.novo` e troca com
  `os.replace` sob uma trava comum com a leitura. `garantir()` só espera o
  Oracle se o CSV não existir; sem o atualizador (scripts, testes) mantém a
  regra antiga de 1 hora.
- Cada resposta mostra "Dados atualizados em DD/MM/AAAA às HH:MM" (o CSV mais
  antigo entre os 4; "(atualizando agora…)" durante uma atualização) —
  guardado com a mensagem, então o histórico mostra de quando era cada dado.
- **Desconto sem período = ano atual, avisando** (decisão de 06/10/2026, troca
  o "pergunte o período" de 02/10): `periodo_padrao: "ano_atual"` em desconto e
  desconto_diario. Vale também quando o desconto vem cruzado (NPS + desconto
  sem período somava desde 2020). O resultado leva `periodo_assumido` e a
  resposta diz "Em 2026 (você não informou o período)… posso consultar outro".
- **Perguntas de relação** ("filiais com NPS acima de 90 dão mais desconto?"):
  sem recurso novo no motor — só instrução: cruzar todos os itens (sem limite)
  e analisar usando apenas os números de cada item (sem média/soma de grupo),
  com exemplos dos dois lados, exceções e linguagem de tendência.

## Análise com execução de código na resposta (06/10/2026)

- Perguntas de relação ("as filiais com NPS acima de 90 dão mais ou menos
  desconto?") pediam contas que a IA não pode fazer de cabeça (% de cada
  grupo, média, mediana, correlação). Sem recurso novo no motor: a resposta
  final (`ai_service.gerar_resposta_final`) liga a **execução de código** do
  Gemini — as contas são feitas por Python sobre os dados do sistema. Se o
  recurso falhar (outro modelo/chave), cai pra chamada sem ferramentas (resposta
  sem contas, nunca erro). Temperatura 0.
- Formato: conclusão → resumo dos grupos (% sobre as somas como principal,
  média simples identificada, mediana, total) → cuidados (correlação, item que
  puxa a média, exceções calculadas no código, sem causa, poucos itens) →
  conclusão prática. Ex 2026: 3,14% x 1,74%, correlação 0,26, sem Parnaíba
  2,70%; exceções Picos (NPS 99,1, 1,21%) e Araguaína (NPS 87,4, 3,64%).
- Testado em 5 execuções seguidas: números principais e exceções certos em
  todas; 1 em 5 trouxe um número secundário não conferido — o modelo
  (gemini-3.5-flash-lite) ainda varia um pouco. Perguntas simples não ficam
  mais lentas (~3-4 s); as de análise levam ~10 s.
- A regra antiga "você pode realizar cálculos simples" foi trocada por "nunca de
  cabeça: use os campos prontos do resultado ou execute código".
- **Linguagem de negócio** (pedido da usuária, 06/10/2026: a 1ª versão só
  "soltava" média, mediana e correlação): as contas continuam no código, mas o
  texto traduz — "quase o dobro", "a relação é fraca: muitas filiais fogem do
  padrão", "mesmo sem Parnaíba continua maior (2,70%)", exceção com o que ela
  sugere —, sem termos técnicos; % de grupo dito como "juntas"; NPS como nota;
  grupo com 1-2 itens → avisa que a comparação é frágil.
- **Conferência dos números da resposta** (`src/conferencia_numeros.py`): todo
  número do texto tem que ser arredondamento/abreviação de um valor dos dados
  (resultado, saída do código, pergunta, histórico); senão a resposta é refeita
  (código, código, sem código — sem código a IA não pode calcular nada). Se
  nenhuma passar, não mostra número nenhum (fica a tabela). Testado: pegou
  2,74%/2,75%/3,12% e totais de grupo errados; perguntas comuns sem alarme falso
  (3-10 s). Limite achado: o gemini-3.5-flash-lite erra muito na análise com
  vários números (3 tentativas erradas seguidas → 18-84 s), e a chave está no
  plano gratuito (3.6-flash: 5 pedidos/min, "alta demanda").
- **Análise enxuta** (opção A, 06/10/2026, até decidir sobre um plano pago do
  Gemini): só 3 números calculados por código — o % de cada grupo e a
  correlação (dita em palavras: fraca/moderada/forte) — e as exceções
  escolhidas pelo código (só o nome; números da tabela). Sem totais de grupo,
  médias ou "sem o item X", que eram os números que o flash-lite errava.
  Testado: números certos e exceções certas (Picos e Araguaína) em 4 de 4;
  8-11 s (uma de 43 s, quando a conferência mandou refazer).
- **Mesmos meses ao comparar o ano atual** (`_mesmos_meses_na_comparacao`):
  "comparar_com" ou agrupar por 2+ anos com o ano atual (incompleto) usa jan até
  o mês anterior em todos os anos. Antes, "filiais que mais cresceram de 2025
  pra 2026" comparava 9 meses com 12 (Timon -27%; agora -5,43%; Parnaíba de
  -12,75% para +18,29%). O resultado leva `mesmo_periodo_nos_anos` e a resposta
  avisa.
- **Tabela de cruzamento**: além do campo da ordem e dos filtros, o campo que
  resume cada indicador (`campo_principal`). O da meta passou a ser o
  atingimento (a variação continua no faturamento, via `campo_variacao`).
- **Tabela de comparação entre períodos intuitiva** (`_colunas_da_comparacao_de_periodos`):
  quando o sistema escolhe as colunas numa comparação entre períodos, o campo do
  foco aparece nos DOIS períodos, com o período no título ("Faturamento
  jan-set/2025", "Faturamento jan-set/2026"), e o quanto mudou como "Cresceu/caiu
  (R$)" (com sinal: +R$ / −R$) ou "Cresceu/caiu (%)"; os outros campos levam o
  período atual entre parênteses ("% Desconto (jan-set/2026)"). Antes:
  "Faturamento (anterior)", "Diferença Faturamento".

## Desconto por produto, família e grupo (07/10/2026)

- **Fonte:** `src/produto_data.py`. `desconto_produto.csv` (~980 mil linhas
  desde 2020, por filial/mês/produto — sem RCA, decisão da usuária) do Oracle,
  mesma conta da 8302; `produtos.csv` com descrição (PCPRODUT) + GRUPO e FAMÍLIA.
  Totais por ano iguais ao desconto mensal (2025 exato).
- **Grupo e família vêm da planilha** BASE_PRODUTOS (não existem no Oracle),
  mantida por um gerente em `\10.0.1.213\0002 - comercial\1 - REUNIÕES\1.1 -
  REUNIÃO SEMANAL\BASE_PRODUTOS` (o "E:" do computador da usuária). Grupo =
  coluna GRUPO_OU_KPI (confirmado pela supervisora). A planilha é copiada pra
  `dados/base_produtos.xlsx` quando muda; sem rede, vale a cópia. Produto fora da
  planilha = "SEM GRUPO" (185 produtos, 0,1% do desconto em 2026); sem família, a
  família é o próprio produto. No servidor, a TI precisa liberar leitura dessa
  pasta pro usuário do serviço.
- **Dimensões** no indicador desconto: "grupo", "familia", "produto" (código =
  um produto; nome = a família dele — se o nome cair em famílias diferentes, a
  que tem as palavras no próprio nome; senão pergunta). Produto e cliente não
  combinam na mesma consulta (arquivos diferentes) — o motor avisa.
- "Mais desconto" ordena pelo valor em R$ (pelo % subiam itens de R$ 68); pelo %
  só quando a pergunta pede.

### Ajustes após os testes do desconto por produto (07/10/2026)

- **Venda bruta** (VLVENDA) nos arquivos de produto e cliente → campo `venda_bruta`
  no desconto. "Os grupos com mais desconto vendem mais?" / "quanto o Mateus
  comprou?" respondem sem cruzar indicador (faturamento e meta não têm
  produto nem cliente). Total 2025 igual nos dois arquivos (R$ 1,013 bi).
- "Produtos sem grupo" = filtro grupo "SEM GRUPO" (instrução na tool).
- `criterio_da_ordem` na resposta do motor ("Ordenado por desconto (valor em
  R$), do maior para o menor dentro de cada filial"): a IA dizia "maior
  percentual" numa lista ordenada pelo valor.
- `mes_atual_incompleto`: lista mês a mês que inclui o mês atual avisa que ele
  está em andamento (outubro com 7 dias "caía" 74%).
- Conferência de números aceita o valor sem sinal ("caiu 2,89%" ← -2,89).

### Faturamento por produto, grupo, família e cliente (07/10/2026)

- `faturamento_data.juntar_devolucao(vendas, cursor, desde, colunas)`: uma função
  só, usada pelos arquivos de produto e de cliente — soma a devolução
  (VIEW_DEVOL_RESUMO_FATURAMENTO, por DTENT) e calcula VENDA_LIQ.
- Catálogo: o indicador faturamento ganhou `fontes_por_dimensao` (os mesmos
  arquivos do desconto) e as dimensões cliente/empresa/produto/familia/grupo.
  Motor sem regra nova, só duas genéricas: campo cuja coluna o arquivo não tem
  fica de fora (peso/notas por produto) e o calculado (toneladas) fica vazio.
- **Correção no faturamento mensal:** a devolução era juntada só onde o RCA teve
  venda no mês/filial (`how="left"`) — a de quem não vendeu sumia (2025: 25
  devoluções, R$ 270.326,73 de faturamento a mais; ex: Timon mar/2025, RCA 8952,
  R$ 79.500). Agora `how="outer"`, igual à 8280: conferido com a exportação da
  8280 (2020–2025) por filial e ano, diferença abaixo de R$ 1. Mensal, produto e
  cliente batem entre si.

### Cruzamento por produto/cliente e análise aberta (07/10/2026)

- `_validar_cruzamento`: além de filial/estado/mês/ano, cruza por QUALQUER
  dimensão que todos os indicadores identificam igual (mesma coluna e mesmo
  resolvedor) — antes só RCA e supervisor. Faturamento × desconto cruzam por
  grupo/família/produto/cliente/empresa; a meta continua recusada.
- Pedido aberto de análise ("analise X por filial"): regra no prompt — resumo
  com o total + 3 a 4 destaques (maior valor, maior/menor %, quem foge do
  padrão, relação entre indicadores), sem listar os itens.
- Percentuais vão pra IA com 2 casas (`_percentuais_como_na_tabela`): com 4
  casas ela cortava (5,6574 → 5,65; tabela 5,66%) e a conferência barrava.

### Análises: corte das 60 linhas, total no cruzamento e texto (07/10/2026)

- `chatbot._limitar_resultados`: sem ordem pedida (e fora de lista no tempo),
  ordena pelo valor em R$ do indicador (`campo_variacao`/`campo_principal`)
  ANTES de cortar em 60 — antes mandava as 60 primeiras do alfabeto. A tabela da
  tela é reordenada junto (mesmos itens que a IA analisou). O aviso diz que
  `total_de_todas_as_linhas` é de TODOS os itens.
- Consulta cruzada agora traz `total_de_todas_as_linhas` (a mesma consulta sem
  agrupar), menos por RCA (lista só de quem tem meta).
- Regras de texto da análise: o índice da relação pode aparecer, explicado em
  palavras ("numa escala de -1 a 1…"); sem adjetivos de julgamento; exceções da
  análise aberta calculadas por código (metade de cima/de baixo); lista cortada
  avisada na 1ª frase; sem rótulos/expressões internas ("sobre as somas").

### Análise sem molde fixo (07/10/2026)

- A regra de análise (ai_service) deixou de ser um formato fixo (duas metades,
  índice, "quem foge do padrão", "indício, não prova", só 3 números). A IA escolhe
  as visões que a pergunta pede: visão geral, concentração, faixas, pontos fora
  da curva, impacto em R$, relação entre indicadores, sazonalidade/tendência.
  Markdown com título, seções e tabela pequena.
- Todo número calculado continua saindo do código e passando pela conferência.
- Fato x suposição (decisão da usuária, opção 2): explicações e próximos passos só
  no fim, no bloco "Possíveis explicações (não estão nos dados)".
- tool_manager: "costuma/geralmente/todo ano" → todos os anos desde 2020, por
  ano e mês, sem acrescentar cliente/produto ("os clientes de Timon" = a filial).
- Qualidade varia com o modelo: o gemini-3.5-flash-lite às vezes escreve contas
  sem calcular (barradas pela conferência) ou repete a lista; o gemini-3.6-flash
  não pôde ser comparado (cota do plano gratuito).
- Princípio geral no topo da regra de análise: "primeiro, responda à pergunta" —
  se ela compara, calcular os dois lados e dizer qual é maior; lista solta não é
  resposta. Sem regra por caso (decisão da usuária: até ter plano pago, só esse
  princípio).

## Reorganização em pastas (08/10/2026)

Mesma estrutura do projeto do supervisor, sem mudar funcionamento:
- `app.py` (~45 linhas) só monta a página; `config/` (settings, constants);
  `ui/` (styles, state, formatacao, components/: cabecalho, barra_lateral, chat,
  tabela).
- `src/` virou `core/`: `services/` (chatbot_service, ia_service,
  conferencia_service, atualizador_service, prompts/, ferramentas/), `motor/`
  (orquestrador, catalogo, motor_metricas, variacao_utils), `repositories/`
  (oracle, azure, arquivos_repository e os *_repository de cada base, filiais,
  perguntas), `models.py` (antigo schemas), `exceptions.py`, `logger.py`.
- Nomes antigos citados nas seções acima: ai_service → core/services/ia_service,
  chatbot → chatbot_service, atualizador → atualizador_service,
  conferencia_numeros → conferencia_service, *_data → core/repositories/*_repository,
  arquivos_oracle → arquivos_repository, connection → oracle, database → azure.
- A pasta dos dados locais passou de `dados/` para `data/` (CSVs, planilha de
  produtos, perguntas.db) — continua fora do git (.gitignore). Onde as seções
  acima dizem `dados/`, leia `data/`.

### Refatoração do orquestrador (08/10/2026)

Sem mudar nenhuma regra: 2.144 → 1.829 linhas (código 1.346 → 1.166;
comentários 413 → 275, mantendo o "por quê" de cada regra).
- `executar_consulta` (423 → 72 linhas) virou um roteiro: `_preparar_consulta`
  → `_ajustar_periodo` → `_consultar` → `_separar_sem_valor`/`_ordenar` →
  `_avisos_para_a_ia` → `_tabela_da_tela`.
- Repetição removida: `_dias`/`_mes_inteiro` (períodos por dia em tabela),
  `_filtros_efetivos(indicador_def, consulta)` lê o período da própria consulta
  (`_do_periodo_comparado` pro "comparar_com"), `_com_filtros`,
  `_com_meses_fechados` (ano incompleto), `_checar_dimensoes`,
  `_atributos_por_item`, `_exibicao_do_campo`, `_chave`, `_inicio_e_fim`; o total
  sem agrupamento usa o mesmo caminho do agrupado (coluna constante).
- Conferido com 266 testes e 42 consultas reais gravadas antes da mudança
  (resultados idênticos, inclusive as mensagens de erro).

### Layout no estilo das IAs (08/10/2026)

Pedido da usuária ("igual ao ChatGPT"), com as cores da Ferronorte:
- Tela inicial (`ui/components/tela_inicial.py`, antes cabecalho.py): saudação no
  meio da tela + 4 sugestões (`config/constants.SUGESTOES`) que fazem a pergunta
  de verdade. Saíram a faixa azul, o cartão "Consultas disponíveis" e os exemplos
  com resposta fixa da barra lateral.
- Pergunta em balão azul-claro à direita (sem avatar); resposta como texto solto
  com o ícone; campo de digitar arredondado com botão azul; "Dados atualizados
  em…" embaixo do campo (`styles.mostrar_data_atualizacao`).
- Barra lateral: "＋ Nova conversa" (limpa o histórico) e "Esta conversa"
  (baixar/copiar).

### Pergunta sobre os itens da resposta anterior (09/10/2026)

"e em quais filiais eles mais deram desconto" (depois de "os RCAs que mais deram
desconto no mês passado") virava o ranking de TODAS as filiais. Regra geral no
prompt de interpretação (prompts/base.py): referência aos itens da resposta
anterior ("eles", "esses RCAs"...) = a mesma consulta (período e itens) com a
nova dimensão, e "os N maiores" vira ordenar_por com "por" + "limite_grupos". Na
resposta (ia_service): se cada item tem um valor só da 2ª dimensão (cada RCA numa
filial), dizer isso em vez de listar como se houvesse várias.
Também: tabela com a 1ª coluna repetida quebrava o alinhamento à direita
(Styler célula a célula) — agora é uma regra por coluna (ui/components/tabela.py).

### Textos das análises e pergunta com vários critérios (09/10/2026)

- NPS é nota: diferença em "pontos", nunca "pontos percentuais" (a regra
  antiga juntava NPS com os percentuais).
- Quantidades com o total ("10 das 18 filiais"). Com filtros_calculados o motor
  manda `quantidade_antes_do_filtro` (quantos havia antes do filtro).
- Vários critérios ("filiais que precisam de mais atenção..."): tool_manager pede
  UMA consulta cruzando os indicadores de todos os critérios, sem limite e sem
  filtro; a resposta define cada corte com o valor do conjunto (calculado pelo
  código — número inventado é barrado) e diz quantos/quais critérios cada item
  atende, em ordem.

### Condições que valem juntas (09/10/2026)

"Queda de faturamento E desconto subindo E NPS caindo" respondia Picos (o NPS dele
subiu): a IA julgava as condições de olho e a conferência só barra NÚMEROS
inventados, não conclusões. Agora (tool_manager) cada condição vira um
filtro_calculado — com comparar_com, sobre "diferenca_{campo}" (< 0 caiu, > 0
subiu); "abaixo da meta" = percentual_atingimento < 100 — e o sistema decide de
forma exata ("nenhuma das 18 filiais"). A conferência também ignora o inteiro 100
(corte da meta), que não está nos dados.
- Quando nenhum item passa em 2+ filtros_calculados, o motor manda
  `mais_perto_do_filtro`: quem atende a todas as condições menos uma e qual
  faltou ("condicao_que_faltou") — a resposta mostra depois do "nenhuma".

### Regras da resposta por assunto (09/10/2026)

As ~536 linhas de regras da resposta (23 seções, todas mandadas em toda
resposta) viraram `core/services/prompts/resposta.py`: seções curtas por assunto
e `regras_da_resposta(resultado, ferramenta)` manda só as que se aplicam ao que
veio nos dados (ex: regras de NPS só com NPS; de meta de tonelada só com ela).
Regras repetidas foram juntadas; as que o motor já escreve nos dados
("periodo_assumido", "criterio_da_ordem", "mes_atual_incompleto"...) viraram
"siga o que o campo diz". Cada resposta recebe 40–110 linhas.
Conferido com uma bateria de 21 perguntas reais pela IA, antes x depois: 19 → 20
certas (a única falha nas duas é "Mateus" ambíguo — o chatbot pergunta qual, o
teste é que esperava um valor), tempo total 170 s → 125 s.
Combinado com a usuária: não criar regra nova a cada erro do modelo — só
corrigir o que der pra resolver no motor, de forma exata e geral.

## Desconto por venda (nota/pedido) — 09/10/2026

- `core/repositories/venda_repository.py` → `data/desconto_venda.csv`: uma linha
  por nota (NUMTRANSVENDA, nota, pedido, data, filial, cliente, RCA, supervisor,
  nº de itens, desconto, tabela, venda), **desde 2025** (decisão da usuária:
  ~700 mil notas/ano; desde 2020 seriam 4,3 milhões). Mesma conta da 8302: 2025
  bate com o mensal até os centavos. Atualizado em segundo plano; em memória até
  o arquivo mudar (abrir leva ~8 s, depois ~0,1–1 s por consulta).
- Dimensão "venda" nos indicadores desconto e desconto_diario (este também
  ganhou cliente/empresa pelo arquivo de venda). Atributos: nota, pedido, data,
  cliente, RCA, filial.
- Nº de nota se repete entre filiais: com filial na pergunta, filtra; sem, e
  em filiais diferentes, pergunta qual (nunca soma vendas diferentes).
- Filtro de venda dispensa o "ano atual" automático (`sem_periodo_padrao_com`).
- Arquivo que "também tem" as dimensões de outro (`tambem_tem`) é escolhido
  quando a pergunta mistura as duas (ex: vendas do Mateus = venda + empresa).
- Regras da resposta: seção VENDA (identificar pela nota, nunca pelo nº interno).

## Excel no formato institucional (09/10/2026)

O botão "⬇️ Baixar em Excel" usa `ui/exportar_excel.py` (`gerar_excel`), no formato do resumo gerencial do supervisor:

- topo do tamanho da tabela: a logo na 1ª linha (em fundo branco, pois as letras azuis sumiam no azul) e, embaixo, a faixa azul com a pergunta como título e, como subtítulo, o período e "Gerado em". Uma pergunta que não cabe na largura da tabela quebra em mais linhas; tabela estreita é alargada até 45 caracteres;
- cabeçalho azul (#0E5EA6), linhas zebradas (#E8F1F9), bordas finas, largura automática e cabeçalho fixo ao rolar.

**Valores como número:** a tabela chega formatada para a tela ("R$ 1.234,56", "2,29%", "1.234"). Nas colunas em que toda célula é valor, o texto volta a ser número, com o formato do Excel (`"R$" #,##0.00`, `0.00%`, `#,##0`), para dar para somar. "sem dados" e "menos de 0,01%" ficam como texto.

**Nome do arquivo:** `Chatbot_Ferronorte_dd.mm.aaaa.xlsx`.

## "Quem menos faturou", nomes dos RCAs e colunas do desconto (09/10/2026)

- **Regra de "menor" por campo ordenado:** `menor_ignora` (catálogo) diz, para cada indicador, quais campos de ordem ela vale (`ordem_por`), o que testar (`campo` < `abaixo_de`) e o `motivo`. A regra fica no desconto (R$ 0,00 de desconto) e no faturamento (RCA com meta cadastrada, mas sem nenhuma venda: `venda_bruta` < 0,01). Quem fica de fora vem em `fora_da_lista_de_menor`, e os totais não mudam. Antes, a regra do desconto valia para qualquer ordem crescente.
- **Nomes dos RCAs:** `core/repositories/rca_repository.py` grava `data/rcas.csv` a partir da PCUSUARI (só leitura), atualizado pelo atualizador. `construir_mapa_rca_nome` usa o nome das vendas (8302) e completa com o cadastro quem nunca vendeu (ex.: 9230, RÔMULO VIENA VERAS).
- **Tabela de cruzamento:** `colunas_no_cruzamento` do desconto mostra o desconto em R$ e em %, não só o %.

## Velocidade: cache dos CSVs, tempo por etapa e etapas na tela (13/10/2026)

- **Cache dos CSVs:** `ler_csv` (`core/repositories/arquivos_repository.py`) guarda cada arquivo lido em memória até ele mudar. A versão é a data + o tamanho do arquivo: quando o atualizador grava um CSV novo, a próxima leitura busca o novo. Quem lê recebe uma cópia, e a guardada nunca é alterada. Ler o desconto por cliente caiu de ~1,7 s para ~0,07 s; as 42 consultas do gabarito, de 38,4 s para 24,5 s, com os resultados idênticos. O desconto por venda continua com o cache próprio, que guarda também as junções com cliente e RCA (~7 s).
- **Tempo por etapa:** `processar_pergunta` (`chatbot_service.py`) grava uma linha no log por pergunta: `Tempo | entender 2.1 s | calcular 0.4 s | escrever 3.2 s | total 5.7 s`. "Entender" é a 1ª chamada ao Gemini, "calcular" é o motor e "escrever" é a 2ª chamada (com a conferência dos números).
- **Etapas na tela:** a bolinha de "digitando" mostra a etapa atual: "Entendendo a pergunta…", "Buscando os dados…", "Escrevendo a resposta…" (parâmetro `avisar_etapa` de `processar_pergunta`).
- **Atualizador em programa separado:** a atualização rodava no mesmo programa do chatbot e segurava o processador (milhões de linhas): "qual o NPS do ano passado?" levou 1min30 durante a completa e 20 s sem ela. Agora `iniciar()` abre `python -m core.services.atualizador_service` à parte. Um atualizador por vez (trava em `data/atualizador.trava`; um novo espera o antigo sair); ele sai quando o chatbot fecha (lê o stdin que o chatbot mantém aberto); "(atualizando agora…)" vem de `data/atualizando.agora`.
- **Completa uma vez por dia:** o dia da última completa fica em `data/ultima_completa.txt`. Ao abrir, se ela já rodou hoje, faz só a parcial (antes, cada reinício refazia os ~10 min da completa).

## Indicador de clientes (13/10/2026)

Regras da supervisora, contadas em dias e olhando as compras em **qualquer
filial** (o cliente é da Ferronorte):

- **ativo**: comprou há menos de 90 dias;
- **em risco de perda**: de 60 a 89 dias sem comprar (continua ativo);
- **inativo**: 90 dias ou mais (até 12 meses);
- **novo**: 1ª compra (desde 2020) no mês;
- **recuperado**: voltou a comprar depois de 90+ dias parado.

"Cliente de Timon/do RCA" = comprou ali nos últimos 12 meses (o PCCLIENT
não tem filial preenchida e o RCA do cadastro só bate em 4% dos casos).
Quem está ativo só por compras em outra filial (outro RCA) é contado à
parte, pra resposta avisar. Cada código de cliente (loja) conta 1.

- **Dados**: `data/compras_clientes.csv` (os dias de compra por
  cliente/filial/RCA desde 2024, da `VIEW_VENDAS_RESUMO_FATURAMENTO` com os
  filtros de venda válida), atualizado pelo atualizador como os outros.
  `core/repositories/situacao_cliente_repository.py` monta a "foto" de cada
  mês desde 2025 na memória (~8 s na 1ª pergunta depois de o arquivo mudar).
- **Motor**: duas peças gerais. Agregação `"nunique"` (conta clientes
  diferentes, sai inteiro) e a opção `"foto_por"` no campo: num período de
  vários meses vale o último mês (ativos "em 2026" = a foto de hoje), em vez
  de somar; agrupado por mês, cada mês tem a sua. A resposta traz
  `situacao_na_data` com a data da foto.
- `periodo_assumido` agora diz o período usado de verdade (no clientes, o
  mês atual), em vez de "o ano atual" fixo.
- `dias_sem_comprar` é campo (agregação `"max"`, foto), não só informação do
  cliente: "os 5 em risco há mais tempo sem comprar" sai ordenado e cortado
  pelo motor (antes a IA escolhia sozinha e errou: havia vários com 89 dias).
  Período assumido num indicador foto diz "vale a situação de hoje".
- Lista mês a mês/ano a ano: a variação é calculada para TODOS os campos
  ("percentual_{campo}_mes_anterior"), não só o principal; a tabela mostra a
  de cada número logo ao lado dele ("Variação Inativos (mês anterior)"). A
  "percentual_mes_anterior" do campo principal continua igual.

## Ano inválido, período da comparação e pontos percentuais (14/10/2026)

- "Ano" que não é ano (a IA mandou `{"ano": [2026, 10]}` querendo outubro)
  agora dá erro claro, em vez de comparar "jan-set de 2026 e 10".
- Sem período na pergunta, o período assumido acompanha a comparação:
  `comparar_com: mes_anterior` → mês atual (antes valia o padrão do
  desconto, o ano atual, e saía "jan-set x setembro").
- Diferença entre dois percentuais aparece como "+2,32 p.p." na tabela.

## Cliente que mais/menos comprou = venda bruta (14/10/2026)

- "Comprou" (cliente) = `venda_bruta`, sem descontar devolução — como a
  rotina 8306 (Análise Cliente RFV), que usa `SUM(VLVENDA)` com os mesmos
  filtros de venda válida do projeto. "Faturou" continua venda − devolução
  (8280). Antes "os clientes que menos compraram" listava faturamento
  negativo (quem devolveu mais do que comprou).
- `menor_ignora` ganhou `motivo_por_dimensao`: "têm meta cadastrada, mas
  não venderam nada" só vale pra RCA; nos outros, "não tiveram venda no
  período (só devolução)".
- `menor_ignora` ganhou `tambem` (outros grupos à parte, cada um com o seu
  motivo, opcionalmente só pra uma ordem): no faturamento, ordenando pelo
  faturamento, quem tem faturamento zero ou negativo (devolveu tudo ou mais
  do que comprou) vem em `tambem_fora`. Ordenando pela venda bruta, fica na
  lista. Totais não mudam.
- O indicador `clientes` não ordena uma contagem de clientes agrupando por
  cliente (campo com `"conta": "cliente"`): cada um teria 0 ou 1.

## Clientes: inativos até 1 ano + parados há mais de 1 ano (14/10/2026)

- Compras dos clientes desde 2020 (`compras_clientes.csv`, ~54 MB; busca
  completa ~2 min 20 s). A foto começa em 2021.
- Inativo = 90 dias a 1 ano (os recuperáveis); `clientes_parados_ha_mais_de_1_ano`
  conta à parte (decisão da usuária: o total de todos os parados desmotivava).
  90 dias = o mesmo do WinThor (`PCCONSUM.NUMDIASCLIINATIV` = 90).
- "Cliente de Timon" = comprou ali nos 12 meses antes da última compra DELE
  (antes: antes de hoje) — o parado há 2 anos continua de onde comprava.
- A foto de cada mês é montada só quando pedida (`carregar` com
  `recebe_filtros = True` recebe os filtros do período; até 24 fotos em
  memória). Todos os meses de uma vez dariam ~10 milhões de linhas.
- `como_ler` no catálogo: o motor manda junto do resultado
  (`como_ler_o_indicador`). A 2ª chamada da IA (que escreve) não lê a
  descrição da ferramenta — por isso "diga também os parados há mais de 1
  ano" não chegava a ela.
- `_aplicar_agrupamento` monta as linhas com `to_dict` (antes `iterrows`):
  a lista de 190 mil clientes caiu de 20 s pra 3 s.
- Clientes parados há mais de N dias: `agrupar_por cliente` + `filtros_calculados`
  em `dias_sem_comprar` (exemplo na descrição da ferramenta); a quantidade é
  quantos atenderam. Sem recurso novo no motor.
- A resposta traz `filtros_sobre_a_metrica` (o critério usado): a conferência
  de números aceita o "730" de "mais de 730 dias", e a IA sabe o critério.
- Avisos reescritos sem jargão ("mostrando 60 de…", "itens antes dos filtros
  sobre a métrica"), que a IA copiava na resposta.
- Ordenar por uma contagem de clientes agrupando por cliente (cada um 0 ou 1)
  não dá mais erro: o motor tira a ordem e segue (o erro bloqueava "os novos
  clientes de Timon" quando a IA pedia essa ordem junto do filtro).

### Prazos "sem comprar há…" e lista de clientes (15/10/2026)

- Leitura dos prazos (decisão da usuária, na descrição da ferramenta): "há 2
  dias" = exatamente 2; "há 2 semanas/meses/anos" = de 2 até completar 3 (2
  meses = 60 a 89 dias); "exatamente" = só aquele; "mais de" = dali pra cima.
  A resposta diz a faixa em dias.
- Campo novo `dias_parado_antes_de_voltar`: o maior tempo que o cliente ficou
  parado antes de uma compra no período (0 = não voltou), de qualquer
  tamanho. "Ficou 5 meses parado e voltou" = esse campo >= 150; antes a IA
  usava os dias sem comprar de HOJE com os recuperados (90+ dias), e errava.
- `dias_sem_comprar` agrupado (empresa, filial) é o MENOR entre as lojas (a
  compra mais recente de qualquer uma): com o maior, o MATEUS saía com 2.142.
- Opção `lista_de_itens` do catálogo (clientes): numa lista agrupada só por
  cliente, `quantos_por_situacao` conta a lista INTEIRA (a IA vê só 60) e,
  sem ordem pedida, a lista vem por dias sem comprar, do menor para o maior
  (`criterio_da_ordem` diz isso; antes o corte em 60 punha os em risco no topo).
- No join dos campos, maior/menor de grupo ausente fica vazio (None), não 0:
  o cliente que voltou em fevereiro e já não é da filial na foto de hoje
  saía "0 dias sem comprar".

### Arquivo diário sai da GFN_MVIEW_VENDAS_ATUAL (15/10/2026)

- A supervisora avisou que a `GFN_MVIEW_VENDAS_ATUAL` (fonte da rotina 8302)
  está desatualizada. Conferido: os dias fechados batem, mas os recentes
  atrasam (14/10/2026: mview R$ 4.419.338,76 x view R$ 4.416.735,76, nota
  cancelada ainda contando; 15/10: vendas mais novas faltando).
- `faturamento_diario.csv` e `faturamento_diario_forma_pagamento.csv` passam a
  vir da `VIEW_VENDAS_RESUMO_FATURAMENTO` com `_FILTRO_VENDA_VALIDA` (a fonte e
  os filtros da 8280 e do mensal), desconto `VLDESCONTO × QT` (por unidade
  nesta view) e nome do RCA do `PCUSUARI`.
- Validado em ago/2026: Timon venda R$ 9.614.269,20, tabela R$ 9.920.150,98,
  desconto R$ 310.567,19 (= mensal); empresa desconto R$ 2.259.420,82;
  líquida Timon R$ 9.588.545,70 x mensal R$ 9.588.545,71 (arredondamento da
  devolução por dia).
- Mais lento: completa ~3 min (diário) e ~4,5 min (forma de pagamento);
  parcial ~20 s cada. Roda em segundo plano.
- O peso continua vindo de `GFN_MVIEW_VENDAS_HIST`/`_ANO_ATUAL` (única fonte de
  peso) — a confirmar com a supervisora se também atrasam.

### Desconto passa a seguir a rotina 8280 (16/10/2026)

- Decisão da usuária (com a supervisora): desconto = venda de tabela − venda
  bruta (`ROUND(SUM(VLTABELA) - SUM(VLVENDA), 2)`), a conta da 8280 sem o
  sinal invertido. Antes era `SUM(VLDESCONTO × QT)` (a conta da 8302), em que
  a venda acima da tabela não abatia o desconto dos outros itens.
- Timon ago/2025: R$ 342.868,14 (8302) → R$ 216.266,75 (= 8280). Nota 136094
  (14/08/2025): R$ 6,35 → R$ 1,78 (= 8280).
- % desconto = desconto ÷ venda bruta (a divisão das duas rotinas); antes ÷
  venda de tabela. Timon ago/2025: 2,09%. O PERCDESC da própria 8280 não foi
  copiado: soma o VLDESCONTO por unidade sem a quantidade (0,09%).
- Desconto negativo = vendeu acima da tabela mais do que descontou. Em "quem
  menos deu desconto" sai da lista com motivo próprio (`menor_ignora` com
  `tambem` pro abaixo de R$ 1,00); os totais somam tudo.
- Vale pra todos os arquivos (mensal, diário, forma de pagamento, cliente,
  produto, venda). Os CSVs existentes foram recalculados a partir das colunas
  VENDA_TABELA e VENDA_BRUTA; o de forma de pagamento (sem coluna de tabela)
  foi gerado de novo do Oracle.
- Por que a 8280 dá menos: ela é um saldo. Na 8302 (arquivo exportado de
  2024–2025), 82.461 de 318.194 linhas por RCA/dia/cobrança têm venda acima
  da tabela; em algumas filiais (Ferroleste João XXIII) são 84% das linhas.
  Linhas fora do normal pesam muito: FN Administração 01/07/2025, R$ 2.050.000
  vendidos com tabela zero.

### Aviso de "outra filial / outro RCA" só no recorte certo (20/10/2026)

- "Clientes ativos em Timon" respondia também "759 só compraram com outro
  RCA", que não cabe numa consulta de filial.
- Nova opção de campo no catálogo, `so_com` (uma dimensão): o campo só sai
  quando a consulta filtra, agrupa ou compara por ela
  (`orquestrador._sem_campos_fora_do_recorte`, também no total).
  `ativos_so_em_outra_filial` = `so_com: filial`; `ativos_so_com_outro_rca` =
  `so_com: rca`. Na empresa toda, nenhum dos dois.

### Lista de clientes inteira na tabela (20/10/2026)

- "Quais clientes estão em risco em Timon" saía com 10 dos 528 na tabela e no
  Excel, e o texto dizia "a lista completa está na tabela". A instrução da
  ferramenta mandava "limite": 10 em toda pergunta sem quantidade. Agora o
  limite 10 é só de ranking ("quem mais/menos", "os maiores"); lista de quem
  atende uma condição vem sem limite (a IA continua recebendo só 60).
- Numa lista agrupada pelo próprio item, as colunas de contagem dele (opção
  "conta" do campo, ex: "Em Risco de Perda" = 1 por cliente) saem da tabela.
- Tabela só de campos "foto": o motor manda `_legenda` ("Situação de hoje,
  20/10/2026"), usada na tela e no Excel no lugar de "Ano: 2026".

### Comparação "anterior" a partir do período da pergunta (20/10/2026)

- `comparar_com` relativo ("mes_anterior", "ano_anterior",
  "mesmo_mes_ano_anterior", "ontem", "semana_anterior") era resolvido a partir
  de HOJE mesmo com período na pergunta: agosto/2024 x "mês anterior" virava
  setembro/2026 e 2025 x "ano anterior" comparava 2025 com ele mesmo.
- Agora, com período definido (filtros ou "personalizado"), o motor troca por
  `comparar_com_personalizado` contado a partir dele
  (`orquestrador._comparacao_a_partir_do_periodo`): ago/2024 → jul/2024;
  jan/2025 → dez/2024; abr–jun → jan–mar; 2025 → 2024; dia → dia anterior;
  semana → 7 dias antes; mês inteiro (por dia) → mês anterior inteiro.
  "Mês anterior" de meses que cruzariam o ano pede o período exato. Sem
  período na pergunta, nada muda.

### Tabela com todas as linhas (20/10/2026)

- `chatbot_service` cortava a tabela da tela em 60 linhas (o mesmo corte do
  que vai pra IA). Agora a tabela leva todas as linhas: o Excel baixa a lista
  inteira e a tela mostra até 100 (`ui/components/tabela.LINHAS_NA_TELA`),
  com "Mostrando 100 de N linhas". A conversa exportada em texto também para
  em 100.
- O aviso de lista cortada que vai pra IA diz que a lista inteira está na
  tabela, que é interno (não repetir "aqui vão 60") e que o texto cita no
  máximo 10, como a regra de LISTAS.
- Lista que fica sem nenhuma coluna de valor depois de tirar a contagem (ex:
  "quais clientes estão em risco") mostra o campo da ordem da lista
  (`lista_de_itens.ordem`, dias sem comprar) — sem coluna de valor a tela não
  mostrava a tabela.

### Última compra por empresa e título CNPJ/CPF (20/10/2026)

- Agrupado por empresa, o indicador clientes traz a data e a filial da última
  compra (`ATRIBUTOS_DIMENSAO["empresa"]`). Os atributos de um item com
  várias linhas (lojas da empresa, cliente em vários meses) vêm da linha mais
  recente por `catalogo.COLUNA_DO_MAIS_RECENTE` (DATA_ULTIMA_COMPRA); antes
  era a primeira linha encontrada.
- A coluna do documento do cliente se chama "CNPJ/CPF" (muitos são CPF).

## Ticket médio (21/10/2026)

- Ticket médio = faturamento (venda − devolução) ÷ nº de notas (definição da supervisora). Derivado `ticket_medio` (`motor_metricas.calcular_ticket_medio`) no `faturamento` e no `faturamento_diario`; como é calculado depois de somar, vários meses = total ÷ total (não média dos tickets).
- Por cliente/empresa: `desconto_cliente.csv` ganhou `QT_NOTAS` (COUNT DISTINCT NUMTRANSVENDA, gerado de novo do Oracle; soma por filial bate com o faturamento mensal). Por produto/família/grupo não existe (uma nota tem vários produtos): o campo vem vazio.
- `gerar_descricao_indicadores` passou a listar também os campos calculados (derivados) — antes a IA só conhecia `percentual_desconto`, `toneladas` etc. pelas regras escritas.

## Frequência de compra (21/10/2026)

- Proposta da usuária, aguardando a supervisora: em média, a cada quantos dias o cliente compra = (última − primeira compra) ÷ (nº de dias com compra − 1), nas compras dos 12 meses até a data da foto, em qualquer filial (mesmo dia = 1 compra; 1 compra só = vazio). `situacao_cliente_repository._frequencia_de_compra` → coluna `FREQUENCIA_DE_COMPRA` da foto.
- Campo `frequencia_de_compra` do indicador `clientes`: foto (com um ano, a de dezembro = aquele ano; sem período, hoje = últimos 12 meses) e `"mean"` com `unico_por` CODCLI — agrupado por filial/empresa, a média dos clientes, cada um uma vez. O motor passou a deixar a média vazia (não 0) num grupo sem linha.
- Tabela por empresa: "Última compra" (atributo de cliente e de empresa) passou a vir depois do nome/CNPJ da empresa — antes, por aparecer primeiro nos atributos do cliente, virava a 1ª coluna. O "como_ler" diz que, no ano atual, a frequência é dos 12 meses até hoje (não só do ano).

## Tabela do cruzamento segue a resposta; "Empresa" virou "Cliente" (21/10/2026)

- Cruzamento sem "colunas" da IA (e sem comparação): o campo principal de um indicador SEM `colunas_no_cruzamento` (ex: clientes_ativos) passou a ser só o padrão. O motor manda `_pela_resposta` ({"opcionais", "extras"}) e as linhas trazem os outros campos; `ui/formatacao._colunas_citadas_na_resposta` mostra as que a resposta cita (palavras ou rótulo do `exibicao`) — "faturamento e frequência" mostra Faturamento | Compra a cada (dias). Nenhuma citada: fica o padrão. As `colunas_no_cruzamento` (desconto R$ e %) continuam fixas.
- O título de `empresa_nome` virou "Cliente" (a empresa pode ser uma pessoa, CPF — ex: Consumidor Final); numa tabela que também tem o nome da loja (`cliente_nome`/`venda_cliente`), continua "Empresa".

## Valor, nota, pedido e RCA da última compra (21/10/2026)

- `situacao_cliente_repository.detalhes_da_ultima_compra`: junta à foto as notas do dia da última compra de cada cliente (`venda_repository.carregar_notas_dos_clientes`, leitura enxuta do `desconto_venda.csv`, desde 2025): valor = soma da venda bruta do dia (o que comprou), notas/pedidos/RCAs juntos em texto ("601 e 602"). Antes de 2025, vazios. Vetorizado: só quem tem várias notas no dia passa pela junção de textos (12 s → 0,9 s).
- Atributos `valor_ultima_compra`, `nota_ultima_compra`, `pedido_ultima_compra`, `rca_ultima_compra` em cliente e empresa (empresa: os da loja que comprou por último). `catalogo.ATRIBUTOS_SO_SE_CITADOS`: esses só entram na tabela quando a resposta usa a palavra ("valor", "nota", "pedido", "rca"/"vendedor") — a lista de clientes não fica larga.
- Frequência na filial (22/10/2026): `FREQUENCIA_NA_FILIAL` = a mesma conta por (cliente, filial); campo `frequencia_na_filial` com `so_com: "filial"` (só numa consulta por filial) e `unico_por` (CODCLI, CODFILIAL). Títulos: "Compra a cada (dias), na filial" / "…, geral". Limite da definição (média dos intervalos): compras concentradas num período curto dão frequência alta mesmo com meses sem comprar depois (SPE Cavalcante em Timon 2025: 6 compras de 06/02 a 21/02 = a cada 3 dias).
- Período da frequência (22/10/2026, usuária): é o da pergunta — um ano = de janeiro até o fim dele (ou hoje, no ano atual); um mês passado = só ele; vários meses = do 1º pedido até a foto; sem período ou só o mês atual = os 12 meses até hoje (`_inicio_da_janela`). A foto guardada traz a de 12 meses; com período, `carregar_situacao_clientes` recalcula só as duas colunas (`_cache["com_periodo"]`, sem copiar a foto, que tem ~80 MB).
- Dias sem comprar na filial (22/10/2026): `DIAS_SEM_COMPRAR_NA_FILIAL` (da última compra NAQUELA filial), campo `dias_sem_comprar_na_filial` com `so_com: "filial"`. O `como_ler` pede a frequência sempre junto com os dias sem comprar (e, por filial, os dois lados), pra mostrar quem está atrasado em relação ao costume.
- Formato da resposta da frequência (22/10/2026, usuária): "No período de <datas>, a frequência de compras do cliente <nome> é de a cada N dias. Está há M dias sem comprar. Se preferir, você pode consultar outro período." (por filial, o geral entre parênteses). As datas vêm prontas: chave `periodo_dos_campos` do indicador (campos, nome do aviso, função) → `orquestrador._avisos_para_a_ia` põe `periodo_da_frequencia` ("23/10/2025 a 22/10/2026", de `situacao_cliente_repository.periodo_da_frequencia`, a mesma regra da conta) quando o resultado tem a frequência.
- Período não informado (22/10/2026, usuária, vale pra todos os indicadores): a resposta começa pelo período usado ("Em outubro de 2026, …" / "No período de … a …, …") e termina com "Se preferir, você pode consultar outro período." — sem "(você não informou o período)" (prompts/resposta.PERIODO_ASSUMIDO). O aviso `periodo_assumido` traz também o período próprio do campo (`periodo_dos_campos["nome"]`: "a frequência de compra usa …").
- Última compra da EMPRESA (22/10/2026): antes vinha da loja mais recente — com várias lojas comprando no mesmo último dia, uma ao acaso (Hiper Farma: R$ 428,05 numa lista, R$ 961,29 em outra). Agora `detalhes_da_ultima_compra` calcula também por (ANO, MES, EMPRESA) as colunas `*_EMPRESA`: o último dia em que alguma loja comprou, com TODAS as lojas daquele dia (valor somado, notas/pedidos/RCAs/filiais juntos, até 3 e "e mais N"); `ATRIBUTOS_DIMENSAO["empresa"]` usa essas colunas. Vem antes de `padronizar_filiais`, depois do merge do cadastro (precisa da EMPRESA); `carregar_notas_dos_clientes` traz a CODFILIAL.
- Aviso `quantidade_antes_do_filtro` reescrito ("São N de M: diga os dois números…") — o texto antigo ("N de M atenderam ao critério") era copiado na resposta.
- `quantidade_antes_do_filtro` (22/10/2026): "N passaram no filtro, de M consultados no total…" — com "São N de M" a IA escreveu "52 de 5.075 clientes novos".

## Participação no total (22/10/2026)

- Opção `participacao` da consulta: {"dentro_de": [dimensões cujo filtro fica no total], "campo": opcional (padrão o principal)}. `orquestrador._participacao` roda a mesma consulta só com o período e os filtros de `dentro_de` (["filial"] = o total de Timon; [] = a empresa toda) e põe em cada linha `participacao` = campo ÷ total × 100; `participacao_sobre` leva o total, o recorte e o como_ler. O recorte depende da pergunta (decisão da usuária). Só campo somado ("sum"); não combina com comparar_com/comparar_filtros.
- Conferido: soma do faturamento por cliente = total da empresa (R$ 0,90 de diferença em 2025). EDP em Timon 2025 = 1,30% (R$ 1.451.888,37 de R$ 112.114.507,37); Timon na empresa = 11,25%; desconto de Timon = 18,02% do desconto da empresa.
- Tabela: coluna "Participação (%)" (spec genérica em `ui/formatacao.CONFIG_TABELA_POR_FERRAMENTA`), logo depois do campo.
- Ajustes (22/10/2026): sem "campo", a participação usa o principal se ele se soma, senão o 1º campo somado (desconto: `valor_desconto`, não o %) — "participação de Timon no desconto" dava erro. O aviso traz `total_de` ("de Timon" / "da empresa toda") e um exemplo de frase; a palavra "recorte" aparecia na resposta.

## Mix de produtos comprados (22/10/2026)

- `core/repositories/cliente_produto_repository.py` → `data/cliente_produto.csv`: venda bruta, desconto, tabela e devolução por filial/ano/mês/cliente/produto, desde 2025 (desde 2020 seriam ~7 milhões de linhas), sem RCA. 2025–out/2026: 1,88 milhão de linhas, 99 MB, 70 s pra gerar, 4 s na 1ª carga (cadastro de cliente/produto juntado como categoria e guardado em memória até o arquivo mudar), ~230 MB. No atualizador (completa/parcial como os outros). Antes de 2025: ValueError com a data de início.
- Conferido: por cliente e por produto, venda bruta e desconto iguais aos arquivos de cliente e de produto (devolução: centavos de arredondamento).
- Motor: `fontes_combinadas` do indicador (faturamento e desconto) — quando a pergunta junta dimensões de fontes diferentes (cliente + produto), vale o arquivo combinado cujo `tambem_tem` cobre todas. Antes: "não dá pra combinar cliente com produto".
- Campo `produtos_diferentes` (nunique de CODPROD) com `conta: "produto"` (agrupado por produto é 1: sai da tabela/ordem) e a opção nova `precisa_de: "produto"`: quando um campo pedido (colunas, ordem, filtro sobre a métrica, participação) precisa de uma dimensão, o arquivo é escolhido como se ela estivesse na pergunta (`orquestrador._dimensoes_dos_campos`) — "quantos produtos diferentes a H S comprou" (180 em 2025), "quantos produtos Timon vendeu" (2.173).
- Dimensão pedida que o arquivo escolhido não tem (ex: RCA no mix) → ConsultaInvalida clara, em vez de KeyError.
- Lista com mais de 60 linhas e sem tabela pronta do motor (ex: "quais produtos o Mateus comprou"): a IA recebia a lista ordenada pelo valor e a tela, a lista na ordem do arquivo (por código). `chatbot_service._limitar_resultados` passou a mandar pra tela a lista inteira já na mesma ordem.
- `ui/formatacao.CONTA_POR_CAMPO`: coluna que conta uma dimensão ("conta" no catálogo) sai da tabela quando a tabela é por essa dimensão — antes só na tabela montada pelo motor; na lista sem tabela pronta, "produtos diferentes = 1" aparecia por produto.

## Frequência de compra: nova definição (23/10/2026)

- Usuária (definição de mercado: "nº médio de vezes que o cliente compra num período"): frequência = **quantas vezes o cliente comprou no período** (dias com compra; várias notas no mesmo dia = 1) + **a média por mês**. Substitui o intervalo médio entre compras: com 2 compras em dias seguidos, a Ediana (352671, 20 e 21/07/2026) aparecia como "a cada 1 dia" e no topo da frequência, parada há 93 dias. Agora: 2 vezes em 2026, 0,21 por mês.
- `_frequencia_de_compra` = nº de dias com compra; `_meses_da_janela` = meses do início (dia 1) até a referência, o último proporcional aos dias (01/01 a 23/10 = 9 + 23/31 = 9,74; um mês inteiro = 1). Colunas `FREQUENCIA_DE_COMPRA`, `COMPRAS_POR_MES` e, por filial, `FREQUENCIA_NA_FILIAL`, `COMPRAS_POR_MES_NA_FILIAL`; campos `frequencia_de_compra`, `compras_por_mes`, `frequencia_na_filial`, `compras_por_mes_na_filial`. Sem compra no período: vazio (fora da média do grupo). Agrupado: média por cliente que comprou.
- Sem período (ou só o mês atual): **o ano atual até hoje** (antes, 12 meses). Com período, o da pergunta, como antes. Limite: "frequência em outubro" no mês atual chega ao motor igual a "sem período" (o período padrão do indicador é o mês atual) e usa o ano.
- Acabou a dúvida do mínimo de compras (2 ou 3): qualquer cliente tem um número.
- Títulos: "Compras no período" / "Compras por mês" (", todas as filiais" / ", na filial").
- Frequência da EMPRESA (23/10/2026, usuária): os dias em que QUALQUER loja dela comprou (Consumidor Final em 2026: 249 vezes; antes, a média das lojas dava "244,33 vezes"). Colunas `*_DA_EMPRESA` (geral e na filial), calculadas no loader depois do cadastro (`_com_frequencia` com EMPRESA na foto; sem empresa, a do próprio cliente). Opção de campo nova no motor, `coluna_com: (dimensão, coluna)` → `orquestrador._colunas_do_item`: usa a outra coluna quando a consulta agrupa pela dimensão, ou filtra por ela sem agrupar pelo que o campo conta (`unico_por`) — empresa filtrada e agrupada por cliente continua com o valor de cada loja.
- Média de um item só vinha "235.0": campo "mean" com valor inteiro sai inteiro (`_aplicar_agrupamento`), e a tabela fica sem casas decimais.
- Busca de cliente pelo nome (`cliente_repository._empresas_pelo_nome`): no começo de uma palavra do nome/fantasia, não no meio — "EDP" achava MEDPLUS e MEDPLAN; agora só a EDP Infraestrutura. "Mateus" continua achando "Armazém Mateus".
- Mensagem de nome repetido: "Encontrei mais de um cliente" (era "empresa"; a lista tem pessoa física).

## Faturamento do dia por cliente (23/10/2026)

- "Qual cliente mais comprou em Timon ontem / na semana passada" dava "não há dados": o faturamento mensal e os clientes não têm dia, e o `faturamento_diario` não tinha cliente (só o `desconto_diario` tinha os dois). O `faturamento_diario` passou a usar o arquivo das notas (`venda_repository.carregar_desconto_venda`, desde 2025) com cliente, empresa ou venda (`fontes_por_dimensao`), como o desconto diário. Esse arquivo não tem devolução: por cliente/dia vêm só venda bruta (o que o cliente "comprou") e desconto — o faturamento líquido fica de fora. Conferido: Timon 22/10/2026, F C Oliveira R$ 255.006,72.
- Descrição da ferramenta: tirada a lista "(filial, estado, rca, dia)" do desconto diário (ele também tem cliente/empresa; as dimensões vêm do catálogo).
- Devolução por cliente (23/10/2026): sem faturamento por cliente/dia, a IA "montou" um (venda bruta − desconto: EDP em Timon R$ 46.566,84 em vez de R$ 48.056,56). Novo `data/devolucao_cliente.csv` (`venda_repository._buscar_devolucao`: VIEW_DEVOL_RESUMO_FATURAMENTO por filial/dia da entrada/cliente/RCA, desde 2025, ~15 mil linhas, atualizado junto com o das notas). `carregar_vendas_com_devolucao` = as notas (QT_NOTAS = 1, VENDA_LIQ = venda bruta) + a devolução em linhas à parte (VENDA_LIQ negativa): somado, o faturamento por cliente/dia. É a fonte do `faturamento_diario` com cliente/empresa; por venda continua só a nota.
- Conferido: Timon 22/10/2026 e set/2026, soma por cliente = faturamento diário (R$ 785.120,44; R$ 9.376.058,23). Em 2025 a soma por cliente dá R$ 112.114.507,38 = o faturamento MENSAL (WinThor); o diário dá R$ 112.217.864,59 — o `faturamento_diario_repository.gerar_tabela` junta a devolução com "left" e perde a de dia/RCA sem venda (R$ 103.357,21 em Timon 2025). Corrigido (usuária): "outer", como o arquivo por forma de pagamento; arquivo regravado (2 min 40 s). Agora Timon 2025 diário = R$ 112.114.507,38 (mensal ,37); empresa 2025 R$ 0,99 de arredondamento.
- Legenda da tabela num período em dias (ex: ontem, semana passada): "Dia: 22/10/2026" / "Período: 12/10/2026 a 18/10/2026" (`_tabela_da_tela`, `_legenda`), em vez do "Ano: 2026" que a tela achava no texto.

## Clientes por dia (23/10/2026)

- "Clientes novos de Timon hoje" dava erro (o indicador só entendia mês) e a IA respondia "não há clientes novos". Opção nova de indicador `aceita_dias` (`orquestrador._granularidade`): num indicador mensal, "hoje", "ontem", "semana_atual", "semana_anterior" ou datas viram o filtro "dia". No `clientes`, dimensão "dia" = `DATA_DA_FOTO`.
- `situacao_cliente_repository`: a foto passou a ser de um período (início, referência) — mês ou dias. Novo = 1ª compra no período (`_primeira_compra`, por dia); recuperado = voltou no período (`_voltas`, por dia; antes por mês). `carregar_situacao_clientes` com filtro "dia" monta `_foto_dos_dias` (guardada no mesmo cache das fotos, ~10 s na 1ª vez); a frequência usa só esses dias. `_meses_da_janela` conta cada mês proporcional aos dias; período menor que 1 mês fica sem média por mês (1 compra num dia dava "31 por mês").
- Conferido: Timon hoje 2 novos (Agromina Grãos, Francisco dos Santos); ontem 6 novos e 12 recuperados; semana passada 45 e 68; outubro continua 129 e 232.
- Achado: a filial 33 não está na planilha de lojas (`filiais_repository.LOJAS`) — tudo dela ficava fora (ex: 6 dos 29 clientes novos de hoje; R$ 32.748,18 vendidos hoje). Resolvido: ver "CD de São Luís (filial 33) somado nas lojas".

## CD de São Luís (filial 33) somado nas lojas (23/10/2026)

Decisão da supervisora: continuam as 18 lojas, mas a venda do CD de São Luís (33, cadastrado 11/11/2025, vende desde 27/05/2026) entra no faturamento — na loja de quem vendeu. O CD não tem RCA próprio: vende pelos RCAs das lojas de São Luís (códigos "F33 <loja>" desde 14/08, antes os códigos da loja). Meta do CD = 0 e sem meta de tonelada.

- Regra (`filiais_repository.FILIAIS_REPASSADAS` + `codigos_das_lojas`, usada por `padronizar_filiais` e pelas compras/notas do indicador de clientes): venda da 33 → loja do supervisor da venda (`COD_SUPERVISOR` da linha; sem ele, o do `COD_RCA` no cadastro). Loja do supervisor = a filial onde está a maioria dos RCAs dele no cadastro (PCUSUARI): 4 → GUAJAJARAS, 5 → AREINHA, 6 → TIBIRI, 27 → ARACAGY, 31 → MAIOBÃO.
- `rcas.csv` passou a ter `COD_SUPERVISOR` e `CODFILIAL` (`rca_repository.carregar_cadastro`). `cliente_produto.csv` e `desconto_produto.csv` passaram a ter `COD_SUPERVISOR` (regerados; +0,04% e +1,5% de linhas).
- 2026 até 23/10: CD R$ 14.551.356,21, repassado R$ 14.540.524,93 (Tibiri 5,59 mi, Guajajaras 3,16 mi, Areinha 2,62 mi, Aracagy 1,59 mi, Maiobão 1,58 mi), igual em todas as bases. Fica fora R$ 10.831,28: supervisores 33 e 36, sem RCA em loja (Edimilson Imperatriz, Arcelia, Adriel FL33, Mikaele F33).
- Os RCAs "F33" continuam códigos à parte (sem meta → fora dos rankings de RCA); juntar com o código da loja do mesmo vendedor é decisão pendente da supervisora.
- Os clientes que compram pelo CD contam na loja do supervisor (novos, recuperados, ativos, frequência).

## Inadimplência (28/10/2026)

Indicador `inadimplencia` ligado (antes só registrado, sem fonte). Regras levantadas com a Controladoria e a supervisora (27–28/10/2026).

- Fonte: view `FNORTE.GFN_VIEW_CONTAS_RECEBER_8188` (a PCPREST não é acessível pelo TICONSULTA). Espelho da rotina 120, sem títulos cancelados e desdobrados (DESD). Conferida com a 120 (Timon, vencimento 01/01/2025 a 26/10/2026, ref. 27/10/2026): 425 títulos / R$ 776.177,46, igual cobrança por cobrança. A carteira da 120 tem ~51 títulos / R$ 115 mil a mais: títulos de 2013 que a view não traz (na base da Controladoria, Timon: 40 / R$ 114.823).
- Base da Controladoria (PostgreSQL `dados_credito`, esquema `inadimplencia`: `titulo_receber` = cópia da view; `titulo_aberto_diario` = foto diária; `faturamento_mensal` = igual ao VENDA_LIQ do chatbot, no centavo): usada só pra conferir. O chatbot não depende dela.
- `inadimplencia_repository`: `data/titulos_receber.csv` (~19 mil títulos, 13 s, sempre inteiro) = vencidos em aberto + pagos só depois do fechamento do mês deles. Na leitura, a partir de hoje:
  - **oficial** (fechamento da Controladoria): todo dia 10 fecha o mês de vencimento de 2 meses antes (10/10 → agosto), com os títulos ainda em aberto nesse dia (`DTPAG` vazio ou depois do dia 10). Mês sem fechamento: oficial zero;
  - **% = oficial ÷ faturamento líquido da filial no mês** (`FATURAMENTO_LIQ`, só meses fechados; campo `unico_por` filial/ano/mês). Por cliente/RCA, o % é a parte dele no faturamento da filial, como na view `vw_top5_clientes_ano_atual` da Controladoria. Mês fechado sem título ganha uma linha só com o faturamento;
  - **em atraso hoje**: vencidos e não pagos agora, com `DIAS_DE_ATRASO`;
  - **risco de bloqueio**: bloqueio com 30 dias de atraso (supervisora); em risco = o título mais atrasado do cliente (em qualquer filial) tem 20 a 29 dias (usuária). `DIAS_PARA_O_BLOQUEIO` = 30 − esse atraso.
- Valor = o do título (VALOR), todas as cobranças (cartão incluído), como a 120. CD 33 → loja do supervisor do RCA. Empresa do cadastro dos clientes; quem não comprou desde 2020, pelo CNPJ do título.
- `periodo_dos_campos` → `fechamento_da_inadimplencia` na resposta (último e próximo fechamento) e `como_ler` com as duas leituras.
- Sem período (usuária, 28/10/2026): o oficial e o faturamento do % são só do último mês fechado (`so_o_ultimo_mes_fechado`, com os filtros passados ao loader); o em atraso hoje junta todos os vencimentos. Antes, "qual a inadimplência de Timon?" somava os fechamentos de todos os meses desde 2017 (R$ 1.946.061,42, 0,33%) — número de nenhum relatório. Agora: agosto/2026, R$ 26.288,79 (0,27%), e R$ 942.906,60 em atraso hoje.
- Por RCA (28/10/2026): sem `rca_requer_meta_cadastrada` — o título fica com o RCA mesmo sem meta ou desligado. Antes, em Timon faltavam 3 RCAs (8673, 8903, 9801; R$ 56.721,09 em atraso) e a soma dos RCAs não fechava com a filial.
- Motor (`orquestrador._sem_linhas_so_da_filial`): linha sem o item agrupado que só traz campo `unico_por` (o faturamento do mês sem título) não vira item "nan" na lista; continua no total.
- Conferido: em atraso hoje por mês de vencimento = foto atual da Controladoria (jan/2025 a ago/2026). Ex: % oficial jan/2026: Araguaína 3,51%, Timon 2,04%, Tibiri 1,65%.
- Pendente: títulos ESTR (valor negativo, R$ −3,5 mi desde 2017; nenhum em aberto hoje) entram no oficial de meses antigos (Timon jul/2025 ficou −R$ 133.774) — conferir com `vw_fat_inad_filial_mes_fechamento` se a Controladoria os conta; histórico de pagamentos (período a definir).
