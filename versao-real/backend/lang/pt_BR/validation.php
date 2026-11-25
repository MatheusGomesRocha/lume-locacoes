<?php

return [
    'accepted' => 'O campo :attribute deve ser aceito.',
    'after_or_equal' => 'O campo :attribute deve ser uma data igual ou posterior a :date.',
    'array' => 'O campo :attribute deve ser uma lista.',
    'before_or_equal' => 'O campo :attribute deve ser uma data igual ou anterior a :date.',
    'boolean' => 'O campo :attribute deve ser verdadeiro ou falso.',
    'date' => 'O campo :attribute não é uma data válida.',
    'date_format' => 'O campo :attribute deve estar no formato :format.',
    'distinct' => 'O campo :attribute tem um valor repetido.',
    'email' => 'O campo :attribute deve ser um e-mail válido.',
    'exists' => 'O valor escolhido em :attribute é inválido ou está inativo.',
    'in' => 'O valor escolhido em :attribute é inválido.',
    'integer' => 'O campo :attribute deve ser um número inteiro.',
    'numeric' => 'O campo :attribute deve ser um número.',
    'required' => 'O campo :attribute é obrigatório.',
    'string' => 'O campo :attribute deve ser um texto.',
    'unique' => 'Já existe um registro com este valor em :attribute.',
    'max' => [
        'numeric' => 'O campo :attribute não pode ser maior que :max.',
        'string' => 'O campo :attribute não pode ter mais de :max caracteres.',
        'array' => 'O campo :attribute não pode ter mais de :max itens.',
    ],
    'min' => [
        'numeric' => 'O campo :attribute deve ser de pelo menos :min.',
        'string' => 'O campo :attribute deve ter pelo menos :min caracteres.',
        'array' => 'O campo :attribute deve ter pelo menos :min item.',
    ],
    'attributes' => [
        'nome' => 'nome', 'tipo' => 'tipo', 'documento' => 'documento', 'email' => 'e-mail', 'telefone' => 'telefone',
        'cidade' => 'cidade', 'observacoes' => 'observações', 'codigo' => 'código', 'categoria' => 'categoria',
        'descricao' => 'descrição', 'valor_diaria' => 'valor da diária', 'valor_reposicao' => 'valor de reposição',
        'quantidade' => 'quantidade', 'ativo' => 'ativo', 'cliente_id' => 'cliente', 'evento' => 'evento',
        'data_retirada' => 'data de retirada', 'data_devolucao' => 'data de devolução', 'desconto' => 'desconto',
        'itens' => 'itens', 'itens.*.produto_id' => 'produto', 'itens.*.quantidade' => 'quantidade do item',
        'pago_em' => 'data do pagamento', 'forma' => 'forma de pagamento', 'pergunta' => 'pergunta',
    ],
];
