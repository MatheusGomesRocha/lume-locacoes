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
        $dados = $request->validate([
            'pergunta' => 'required|string|min:2|max:500',
            // Contexto da conversa: o front manda, o Laravel só repassa (a API Python não guarda nada).
            'historico' => 'sometimes|nullable|array|max:6',
            'historico.*' => 'nullable|string|max:500',
            'ultimo_id' => 'sometimes|nullable|string|max:80',
        ]);

        $corpo = ['pergunta' => $dados['pergunta']];
        $historico = array_values(array_filter($dados['historico'] ?? [], fn ($p) => is_string($p) && trim($p) !== ''));
        if ($historico) {
            $corpo['historico'] = $historico;
        }
        if (! empty($dados['ultimo_id'])) {
            $corpo['ultimo_id'] = $dados['ultimo_id'];
        }

        try {
            $resposta = $this->api()->post('/chat', $corpo);

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
