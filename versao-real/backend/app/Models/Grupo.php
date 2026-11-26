<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Grupo extends Model
{
    protected $fillable = ['nome', 'descricao', 'permissoes', 'sistema'];

    protected $casts = ['permissoes' => 'array', 'sistema' => 'boolean'];

    public function usuarios(): HasMany
    {
        return $this->hasMany(Usuario::class);
    }
}
