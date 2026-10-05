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
- **"Quem MENOS deu desconto"** (`menor_ignora_abaixo_de` em desconto e
  desconto_diario; `orquestrador._separar_sem_valor`): em ordem crescente,
  quem tem desconto abaixo de R$ 1,00 sai da lista e vem em `sem_desconto`
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
