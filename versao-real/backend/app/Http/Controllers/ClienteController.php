<?php

namespace App\Http\Controllers;

use App\Exceptions\RegraDeNegocioException;
use App\Models\Cliente;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ClienteController extends Controller
{
    private const REGRAS = [
        'nome' => 'required|string|max:150',
        'tipo' => 'required|in:PF,PJ',
        'documento' => 'nullable|string|max:30',
        'email' => 'nullable|email|max:150',
        'telefone' => 'nullable|string|max:30',
        'cidade' => 'nullable|string|max:100',
        'observacoes' => 'nullable|string|max:2000',
    ];

    public function index(Request $request)
    {
        $busca = trim((string) $request->query('q', ''));

        $consulta = Cliente::query()
            ->when($busca !== '', fn ($q) => $q->where(fn ($w) => $w
                ->where('nome', 'like', "%$busca%")
                ->orWhere('documento', 'like', "%$busca%")
                ->orWhere('email', 'like', "%$busca%")
                ->orWhere('cidade', 'like', "%$busca%")))
            ->orderBy('nome');

        return $this->listaPaginada($request, $consulta);
    }

    public function store(Request $request): JsonResponse
    {
        return response()->json(Cliente::create($request->validate(self::REGRAS)), 201);
    }

    public function show(Cliente $cliente): Cliente
    {
        return $cliente;
    }

    public function update(Request $request, Cliente $cliente): Cliente
    {
        $cliente->update($request->validate(self::REGRAS));

        return $cliente;
    }

    public function destroy(Cliente $cliente)
    {
        if ($cliente->orcamentos()->exists()) {
            throw new RegraDeNegocioException('Este cliente já tem orçamentos e não pode ser excluído.', [], 409);
        }

        $cliente->delete();

        return response()->noContent();
    }
}
