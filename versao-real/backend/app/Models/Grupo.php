<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Grupo extends Model
{
    protected $appends = ['criado_em'];

    protected $fillable = ['nome', 'descricao', 'permissoes', 'sistema'];

    protected $casts = ['permissoes' => 'array', 'sistema' => 'boolean'];

    public function usuarios(): HasMany
    {
        return $this->hasMany(Usuario::class);
    }

    /** O front usa `criado_em` (data do cadastro); o banco guarda `created_at`. */
    public function getCriadoEmAttribute(): ?string
    {
        return $this->created_at?->toIso8601String();
    }
}
