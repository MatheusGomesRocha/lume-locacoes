<?php

namespace App\Exceptions;

use Exception;
use Illuminate\Http\JsonResponse;

/**
 * Erro previsto pelas regras do sistema (ex.: "orçamento aprovado não pode ser editado").
 * Vira uma resposta JSON com a mensagem para o usuário, sem registrar como falha no log.
 */
class RegraDeNegocioException extends Exception
{
    public function __construct(string $mensagem, public array $detalhes = [], public int $status = 422)
    {
        parent::__construct($mensagem);
    }

    public function report(): bool
    {
        return true; // true = já tratado, não vai para o log de erros
    }

    public function render(): JsonResponse
    {
        return response()->json(['message' => $this->getMessage(), 'detalhes' => $this->detalhes], $this->status);
    }
}
