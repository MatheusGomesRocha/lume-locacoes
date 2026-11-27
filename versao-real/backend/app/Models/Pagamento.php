<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Pagamento extends Model
{
    public const PENDENTE = 'pendente';
    public const PAGO = 'pago';
    public const CANCELADO = 'cancelado';

    public const FORMAS = ['pix', 'cartao', 'boleto', 'dinheiro'];

    protected $fillable = ['orcamento_id', 'valor', 'vencimento', 'pago_em', 'forma', 'status'];

    protected $casts = ['valor' => 'float'];

    protected $appends = ['situacao', 'criado_em'];

    /** Pendente com vencimento passado aparece como "atrasado" (não existe como status gravado). */
    public function getSituacaoAttribute(): string
    {
        if ($this->status === self::PENDENTE && $this->vencimento < now()->toDateString()) {
            return 'atrasado';
        }

        return $this->status;
    }

    public function orcamento(): BelongsTo
    {
        return $this->belongsTo(Orcamento::class);
    }

    /** O front usa `criado_em` (data do cadastro); o banco guarda `created_at`. */
    public function getCriadoEmAttribute(): ?string
    {
        return $this->created_at?->toIso8601String();
    }
}
