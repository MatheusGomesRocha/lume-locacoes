<?php

namespace App\Services;

use App\Exceptions\RegraDeNegocioException;
use App\Models\Pagamento;

class FinanceiroService
{
    /** Registra o recebimento de uma cobrança pendente. */
    public function baixar(Pagamento $pagamento, string $pagoEm, string $forma): Pagamento
    {
        if ($pagamento->status !== Pagamento::PENDENTE) {
            throw new RegraDeNegocioException('Só cobranças pendentes podem receber pagamento.', [], 409);
        }

        $pagamento->update(['status' => Pagamento::PAGO, 'pago_em' => $pagoEm, 'forma' => $forma]);

        return $pagamento->fresh('orcamento.cliente');
    }
}
