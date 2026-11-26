"""Evolução assistida do catálogo de consultas: 3 Agents + checagens fixas + aprovação do Master.

  Agent 1 (Analista)   lê as perguntas sem resposta e PROPÕE a solução.
  Agent 2 (Construtor) cria a consulta (busca, regras, permissão) a partir da proposta.
  Agent 3 (Tester)     compara proposta + checagens fixas com o que foi criado; o resultado esperado é
                       escrito e SELADO antes de qualquer execução.
  Master               vê o relatório completo e aprova ou reprova. Nada entra no catálogo sem ele.
"""
