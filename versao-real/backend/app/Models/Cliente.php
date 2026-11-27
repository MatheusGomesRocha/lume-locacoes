<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Cliente extends Model
{
    protected $fillable = ['nome', 'tipo', 'documento', 'email', 'telefone', 'cidade', 'observacoes'];

    /** O front usa `criado_em` (data do cadastro); o banco guarda `created_at`. */
    protected $appends = ['criado_em'];

    public function getCriadoEmAttribute(): ?string
    {
        return $this->created_at?->toIso8601String();
    }

    public function orcamentos(): HasMany
    {
        return $this->hasMany(Orcamento::class);
    }
}
