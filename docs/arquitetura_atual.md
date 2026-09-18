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
várias ferramentas específicas — mas **não substitui tudo**: NPS continua
com ferramenta própria de propósito, porque a fonte de dado dele é
estruturalmente diferente (SQL agregado via cursor, não CSV/pandas).

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

## O que continua com ferramenta antiga, e por quê

| Indicador | Motivo de não estar no motor genérico ainda |
|---|---|
| `nps` | Vem de Azure SQL via cursor manual, não de um DataFrame pandas — precisa de um loader novo antes de caber no motor genérico. |
| `desconto`, `inadimplencia`, `clientes` | Registrados no catálogo (documentando o que o sistema deveria ter), mas sem nenhuma fonte de dado real conectada ainda. **Atenção `desconto`:** cheguei a cogitar usar `VENDA_BRUTA`/`VENDA_LIQ`/`VALORDESC` da base de faturamento, mas conferi contra dado real e a diferença entre `VENDA_BRUTA − VENDA_LIQ` e `VALORDESC` chega a R$ 1,16 milhão em algumas linhas — não é a mesma fórmula do documento ("Fat. Tabela − Fat. Líquido"). Fica pendente até a definição exata ser confirmada. |

## Ferramentas registradas: antes x depois

- Antes da migração: 10 ferramentas.
- Hoje: **5** — `consultar_dados_comerciais`, `consultar_indicadores_nps`,
  `consultar_evolucao_nps`, `verificar_rca`, `listar_filiais`.
- Removidas por serem 100% cobertas pela ferramenta nova (confirmado com
  dado real E com a IA escolhendo a ferramenta certa, não só "deveria
  funcionar"): `consultar_indicadores_faturamento`,
  `consultar_indicadores_faturamento_diario`, `consultar_metas`,
  `consultar_meta_tonelada`, `consultar_crescimento_abaixo_meta`,
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
- `listar_filiais_faturamento` foi pra dentro de `faturamento_data.py`.
- `listar_filiais_faturamento_diario` e `resolver_nome_filial_diario` foram
  pra dentro de `faturamento_diario_data.py` (que já tinha as outras
  resoluções, de RCA).
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

1. **Perguntas que cruzam indicadores de verdade não funcionam ainda** (ex:
   "qual filial teve o maior NPS e também bateu a meta"). O pipeline hoje
   (`src/chatbot.py`) só permite a IA chamar UMA ferramenta por pergunta. O
   plano original previa a IA poder chamar a ferramenta mais de uma vez antes
   da resposta final — essa parte ainda não foi implementada.

## Testes

`tests/test_motor_metricas.py`, `tests/test_orquestrador.py` (motor
genérico) e `tests/test_app.py` (regressão da tabela) — testes novos, todos
passando. Suíte completa: 131 passando, 9 falhas pré-existentes (não
relacionadas a essa migração — confirmado rodando a suíte no `main` antes
de qualquer mudança). O total de testes oscila porque os das funções
mortas são removidos junto com elas — não é perda de cobertura.
