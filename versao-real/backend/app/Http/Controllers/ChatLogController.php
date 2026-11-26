<?php

namespace App\Http\Controllers;

use App\Models\ChatLog;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

/** Registro das conversas com o assistente (observabilidade). Guarda a pergunta e a resposta, nunca os dados lidos pelas consultas. */
class ChatLogController extends Controller
{
    public const TIPOS = ['ajuda', 'consulta', 'cadastro', 'exclusao', 'nao_encontrou', 'erro'];

    public const LIMITE = 500;

    public function index(Request $request)
    {
        return ChatLog::query()
            ->when($request->query('tipo'), fn ($q, $t) => $q->where('tipo', $t))
            ->when($request->query('feedback'), fn ($q, $f) => $q->where('feedback', $f))
            ->orderByDesc('id')
            ->limit(self::LIMITE)
            ->get();
    }

    public function store(Request $request): JsonResponse
    {
        $dados = $request->validate([
            'pergunta' => 'required|string|max:500',
            'resposta' => 'present|string|max:2000',
            'tipo' => ['required', Rule::in(self::TIPOS)],
            'fonte_id' => 'nullable|string|max:100',
            'ferramenta' => 'nullable|string|max:60',
            'gerada_por_llm' => 'boolean',
            'em_cache' => 'boolean',
            'usou_contexto' => 'boolean',
            'latencia_ms' => 'integer|min:0|max:600000',
            'voltas' => 'integer|min:1|max:5',
        ]);

        return response()->json(ChatLog::create($dados)->fresh(), 201);
    }

    public function update(Request $request, ChatLog $chatLog): ChatLog
    {
        $dados = $request->validate([
            'feedback' => ['sometimes', 'nullable', Rule::in(['positivo', 'negativo'])],
            'desfecho' => ['sometimes', 'nullable', Rule::in(['concluido', 'cancelado', 'recusado'])],
        ]);
        $chatLog->update($dados);

        return $chatLog;
    }

    public function destroy()
    {
        ChatLog::query()->delete();

        return response()->noContent();
    }
}
