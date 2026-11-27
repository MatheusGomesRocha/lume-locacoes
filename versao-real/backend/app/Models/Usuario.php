<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Usuario extends Model
{
    protected $appends = ['criado_em'];

    public const MASTER = 'master';

    public const ADMIN = 'admin';

    public const USUARIO = 'usuario';

    protected $table = 'usuarios';

    protected $fillable = ['nome', 'email', 'senha', 'papel', 'grupo_id', 'ativo'];

    protected $hidden = ['senha'];

    protected $casts = ['ativo' => 'boolean'];

    public function grupo(): BelongsTo
    {
        return $this->belongsTo(Grupo::class);
    }

    public function tokens(): HasMany
    {
        return $this->hasMany(TokenAcesso::class);
    }

    /** Formato que o front espera: sem senha, com o nome do grupo. */
    public function paraApi(): array
    {
        return [
            'id' => $this->id,
            'nome' => $this->nome,
            'email' => $this->email,
            'papel' => $this->papel,
            'grupo_id' => $this->grupo_id,
            'grupo' => $this->grupo ? ['id' => $this->grupo->id, 'nome' => $this->grupo->nome] : null,
            'criado_em' => $this->criado_em,
            'ativo' => $this->ativo,
        ];
    }

    /** O front usa `criado_em` (data do cadastro); o banco guarda `created_at`. */
    public function getCriadoEmAttribute(): ?string
    {
        return $this->created_at?->toIso8601String();
    }
}
