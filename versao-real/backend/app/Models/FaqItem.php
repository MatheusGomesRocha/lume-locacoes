<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class FaqItem extends Model
{
    protected $table = 'faq_itens';

    protected $fillable = ['modulo', 'pergunta', 'resposta', 'palavras_chave'];

    protected $casts = ['palavras_chave' => 'array'];

    protected $appends = ['criado_em'];

    protected $hidden = ['created_at', 'updated_at'];

    public function getCriadoEmAttribute(): ?string
    {
        return $this->created_at?->toIso8601String();
    }
}
