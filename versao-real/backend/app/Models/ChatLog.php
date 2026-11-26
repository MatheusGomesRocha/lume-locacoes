<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class ChatLog extends Model
{
    protected $fillable = [
        'pergunta', 'resposta', 'tipo', 'fonte_id', 'ferramenta', 'gerada_por_llm', 'em_cache',
        'usou_contexto', 'latencia_ms', 'voltas', 'feedback', 'desfecho', 'tokens_entrada', 'tokens_saida', 'custo_usd', 'versao',
    ];

    protected $casts = [
        'gerada_por_llm' => 'boolean',
        'em_cache' => 'boolean',
        'usou_contexto' => 'boolean',
        'latencia_ms' => 'integer',
        'voltas' => 'integer',
        'tokens_entrada' => 'integer',
        'tokens_saida' => 'integer',
        'custo_usd' => 'float',
    ];

    /** O front usa `criado_em`; o banco guarda `created_at`. */
    protected $appends = ['criado_em'];

    protected $hidden = ['created_at', 'updated_at'];

    public function getCriadoEmAttribute(): ?string
    {
        return $this->created_at?->toIso8601String();
    }
}
