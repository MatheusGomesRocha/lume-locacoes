<?php

namespace App\Models;

use App\Services\OrcamentoService;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Orcamento extends Model
{
    public const RASCUNHO = 'rascunho';
    public const ENVIADO = 'enviado';
    public const APROVADO = 'aprovado';
    public const FINALIZADO = 'finalizado';
    public const CANCELADO = 'cancelado';

    public const STATUS = [self::RASCUNHO, self::ENVIADO, self::APROVADO, self::FINALIZADO, self::CANCELADO];

    protected $fillable = ['numero', 'cliente_id', 'evento', 'data_retirada', 'data_devolucao', 'status', 'desconto', 'total', 'observacoes'];

    // As datas ficam como texto AAAA-MM-DD de propósito: comparar texto é igual em SQLite e MySQL.
    protected $casts = ['desconto' => 'float', 'total' => 'float'];

    protected $appends = ['diarias'];

    public function getDiariasAttribute(): int
    {
        return OrcamentoService::diarias($this->data_retirada, $this->data_devolucao);
    }

    public function cliente(): BelongsTo
    {
        return $this->belongsTo(Cliente::class);
    }

    public function itens(): HasMany
    {
        return $this->hasMany(OrcamentoItem::class);
    }

    public function pagamentos(): HasMany
    {
        return $this->hasMany(Pagamento::class);
    }
}
