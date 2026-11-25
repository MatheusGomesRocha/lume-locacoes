<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Produto extends Model
{
    protected $fillable = ['codigo', 'nome', 'categoria', 'descricao', 'valor_diaria', 'valor_reposicao', 'quantidade', 'ativo'];

    protected $casts = [
        'valor_diaria' => 'float',
        'valor_reposicao' => 'float',
        'quantidade' => 'integer',
        'ativo' => 'boolean',
    ];

    public function itens(): HasMany
    {
        return $this->hasMany(OrcamentoItem::class);
    }
}
