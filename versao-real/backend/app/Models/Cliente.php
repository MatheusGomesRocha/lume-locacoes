<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Cliente extends Model
{
    protected $fillable = ['nome', 'tipo', 'documento', 'email', 'telefone', 'cidade', 'observacoes'];

    public function orcamentos(): HasMany
    {
        return $this->hasMany(Orcamento::class);
    }
}
