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

    /** O front usa `criado_em` (data do cadastro); o banco guarda `created_at`. */
    protected $appends = ['criado_em'];

    public function getCriadoEmAttribute(): ?string
    {
        return $this->created_at?->toIso8601String();
    }

    public function itens(): HasMany
    {
        return $this->hasMany(OrcamentoItem::class);
    }
}
