<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

/** Uma proposta dos Agents (relatório completo) e o que o master decidiu sobre ela. */
class EvolucaoProposta extends Model
{
    protected $table = 'evolucao_propostas';

    protected $fillable = ['codigo', 'titulo', 'status', 'ativa', 'veredito', 'relatorio', 'decidida_por', 'decidida_em'];

    protected $casts = ['relatorio' => 'array', 'ativa' => 'boolean', 'decidida_em' => 'datetime'];

    /** O que o front recebe: o relatório dos Agents + o estado que só o servidor decide. */
    public function paraFront(): array
    {
        return array_merge($this->relatorio, [
            'id' => $this->codigo,
            'status' => $this->status,
            'ativa' => $this->ativa,
            'decisao' => $this->decidida_por ? ['por' => $this->decidida_por, 'em' => $this->decidida_em?->toIso8601String()] : null,
            'criado_em' => $this->created_at?->toIso8601String(),
        ]);
    }

    /** As consultas aprovadas e ativas (specs, nunca código). Sem as colunas pesadas além do relatório. */
    public static function specsAtivas(int $limite = 30): array
    {
        return static::query()->where('status', 'aprovada')->where('ativa', true)->orderBy('id')->limit($limite)->get()
            ->map(fn (self $p) => $p->relatorio['pacote']['spec'] ?? null)->filter()->values()->all();
    }
}
