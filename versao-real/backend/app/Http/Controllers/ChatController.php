<?php

namespace App\Http\Controllers;

use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Throwable;

/**
 * O navegador conversa com este controller, e ele repassa a pergunta para a API Python (ia-api).
 * Assim a API de IA não fica exposta e o token (se houver) nunca chega ao navegador.
 */
class ChatController extends Controller
{
    private function api()
    {
        $http = Http::baseUrl(config('services.ia.url'))->timeout(10)->acceptJson();

        return config('services.ia.token') ? $http->withHeaders(['X-API-Token' => config('services.ia.token')]) : $http;
    }

    /** Algumas perguntas do FAQ para o usuário começar. Se a API estiver fora do ar, devolve lista vazia. */
    public function sugestoes(): JsonResponse
    {
        try {
            $resposta = $this->api()->get('/faq');

            if ($resposta->successful()) {
                return response()->json(collect($resposta->json())->pluck('pergunta')->shuffle()->take(6)->values());
            }
        } catch (Throwable $e) {
            Log::warning('Chat IA: não foi possível carregar o FAQ: ' . $e->getMessage());
        }

        return response()->json([]);
    }

    public function perguntar(Request $request): JsonResponse
    {
        $dados = $request->validate(['pergunta' => 'required|string|min:2|max:500']);

        try {
            $resposta = $this->api()->post('/chat', ['pergunta' => $dados['pergunta']]);

            if ($resposta->successful()) {
                return response()->json($resposta->json());
            }

            Log::error('Chat IA: a API respondeu ' . $resposta->status());
        } catch (Throwable $e) {
            Log::error('Chat IA: falha ao chamar a API: ' . $e->getMessage());
        }

        return response()->json([
            'encontrou' => false,
            'resposta' => 'O assistente está indisponível no momento. Tente novamente em instantes.',
            'fonte' => null,
            'confianca' => 0,
            'relacionadas' => [],
        ], 503);
    }
}
