<?php

namespace App\Http\Controllers;

use App\Models\FaqItem;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

/** Base de ajuda escrita pelo master. As rotas ficam atrás do middleware `master`. */
class FaqController extends Controller
{
    public const MODULOS = ['Orçamentos', 'Financeiro', 'Produtos', 'Clientes', 'Painel', 'Acesso', 'Assistente', 'Versão de demonstração'];

    /** Máximo de itens extras enviados à ia-api (ela recusa mais que isso). */
    public const LIMITE = 100;

    private function validar(Request $request): array
    {
        $d = $request->validate([
            'modulo' => ['required', Rule::in(self::MODULOS)],
            'pergunta' => 'required|string|min:3|max:200',
            'resposta' => 'required|string|min:3|max:1500',
            'palavras_chave' => 'sometimes|nullable|array|max:20',
            'palavras_chave.*' => 'nullable|string|max:200',
        ]);
        $d['palavras_chave'] = array_values(array_unique(array_filter(array_map('trim', array_filter($d['palavras_chave'] ?? [], 'is_string')))));

        return $d;
    }

    public function index()
    {
        return FaqItem::query()->orderByDesc('id')->get();
    }

    public function store(Request $request): JsonResponse
    {
        if (FaqItem::count() >= self::LIMITE) {
            return response()->json(['message' => 'O limite de ' . self::LIMITE . ' respostas extras foi atingido. Exclua alguma antes de criar outra.'], 422);
        }

        return response()->json(FaqItem::create($this->validar($request))->fresh(), 201);
    }

    public function update(Request $request, FaqItem $faqItem): FaqItem
    {
        $faqItem->update($this->validar($request));

        return $faqItem;
    }

    public function destroy(FaqItem $faqItem)
    {
        $faqItem->delete();

        return response()->noContent();
    }
}
