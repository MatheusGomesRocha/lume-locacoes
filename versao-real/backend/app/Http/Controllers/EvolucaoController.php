<?php

namespace App\Http\Controllers;

use App\Models\ChatLog;
use App\Models\EvolucaoProposta;
use App\Models\FaqItem;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Throwable;

/**
 * Evolução assistida: os 3 Agents (ia-api) propõem consultas novas para as perguntas sem resposta e o master decide.
 * Nada vale sem o "aprovar" dele, e a aprovação refaz as checagens fixas na API antes de ativar.
 * Só o master analisa e decide (middleware `master`); o catálogo ativo é lido por quem usa o assistente.
 */
class EvolucaoController extends Controller
{
    public const MAX_PERGUNTAS = 5;

    private function api(int $segundos)
    {
        $http = Http::baseUrl(config('services.ia.url'))->timeout($segundos)->acceptJson();

        return config('services.ia.token') ? $http->withHeaders(['X-API-Token' => config('services.ia.token')]) : $http;
    }

    private static function normalizar(string $t): string
    {
        return trim(preg_replace('/[^a-z0-9]+/', ' ', Str::ascii(mb_strtolower($t))));
    }

    /** Consultas aprovadas e ativas: é o que o chat pode executar. */
    public function catalogo(): JsonResponse
    {
        return response()->json(EvolucaoProposta::specsAtivas());
    }

    public function index(): JsonResponse
    {
        return response()->json(EvolucaoProposta::query()->orderByDesc('id')->get()->map->paraFront()->values());
    }

    /** Perguntas sem resposta que ainda valem analisar: não respondidas, não ignoradas e sem proposta em andamento. */
    private function perguntasParaAnalisar(): array
    {
        $respondidas = FaqItem::query()->get(['pergunta', 'palavras_chave'])
            ->flatMap(fn ($i) => array_merge([$i->pergunta], $i->palavras_chave ?? []))->map(fn ($t) => self::normalizar((string) $t))->flip()->all();
        $tratadas = EvolucaoProposta::query()->where('status', '!=', 'reprovada')->get()
            ->flatMap(fn ($p) => $p->relatorio['perguntas'] ?? [])->map(fn ($t) => self::normalizar((string) $t))->flip()->all();

        $grupos = [];
        $logs = ChatLog::query()->where('tipo', 'nao_encontrou')->where(fn ($q) => $q->whereNull('desfecho')->orWhere('desfecho', '!=', 'ignorado'))->get(['pergunta']);
        foreach ($logs as $l) {
            $chave = self::normalizar($l->pergunta);
            if (strlen($chave) < 4 || isset($respondidas[$chave]) || isset($tratadas[$chave])) {
                continue;
            }
            $grupos[$chave] ??= ['pergunta' => mb_substr($l->pergunta, 0, 300), 'tipo' => 'dados', 'vezes' => 0];
            $grupos[$chave]['vezes']++;
        }
        usort($grupos, fn ($a, $b) => $b['vezes'] <=> $a['vezes']);

        return array_slice($grupos, 0, self::MAX_PERGUNTAS);
    }

    public function analisar(): JsonResponse
    {
        $perguntas = $this->perguntasParaAnalisar();
        if (! $perguntas) {
            return response()->json(['novos' => [], 'semPerguntas' => true]);
        }

        try {
            $resposta = $this->api(170)->post('/evolucao/propor', [
                'perguntas' => $perguntas,
                'catalogo' => EvolucaoProposta::specsAtivas(),
                'proximo_numero' => ((int) EvolucaoProposta::max('id')) + 1,
            ]);
        } catch (Throwable $e) {
            Log::error('Evolução: falha ao chamar a API: ' . $e->getMessage());

            return response()->json(['message' => 'Não foi possível falar com a API de IA agora. Tente de novo em instantes.'], 502);
        }
        if (! $resposta->successful()) {
            Log::error('Evolução: a API respondeu ' . $resposta->status());

            return response()->json(['message' => (string) ($resposta->json('detail') ?: 'A API de IA não respondeu como esperado.')], $resposta->status() === 503 ? 503 : 502);
        }

        $novos = [];
        foreach ((array) $resposta->json('relatorios') as $rel) {
            if (! is_array($rel) || empty($rel['id']) || EvolucaoProposta::where('codigo', $rel['id'])->exists()) {
                continue;
            }
            $novos[] = EvolucaoProposta::create([
                'codigo' => (string) $rel['id'], 'titulo' => mb_substr((string) ($rel['titulo'] ?? '(sem título)'), 0, 200),
                'veredito' => $rel['veredito'] ?? null, 'relatorio' => $rel,
            ])->paraFront();
        }

        return response()->json(['novos' => $novos, 'semPerguntas' => false]);
    }

    public function decidir(Request $request, string $codigo): JsonResponse
    {
        $d = $request->validate(['aprovar' => 'required|boolean']);
        $p = EvolucaoProposta::where('codigo', $codigo)->firstOrFail();
        if ($p->status !== 'pendente') {
            return response()->json(['message' => "Esta proposta já foi decidida ({$p->status})."], 422);
        }

        if ($d['aprovar']) {
            $spec = $p->relatorio['pacote']['spec'] ?? null;
            if (! $spec) {
                return response()->json(['message' => 'Não há consulta para aprovar: este item é só registro.'], 422);
            }
            if ($p->veredito === 'reprovar_recomendado') {
                return response()->json(['message' => 'O Tester encontrou bloqueios ou testes que falharam: reprove esta proposta.'], 422);
            }
            // Refaz as checagens fixas agora (sem modelo): o que está guardado pode ter sido mexido. Sem resposta da API, não aprova.
            try {
                $c = $this->api(25)->post('/evolucao/checar', ['spec' => $spec, 'proposta' => ($p->relatorio['proposta'] ?? null) ?: new \stdClass(), 'catalogo' => EvolucaoProposta::specsAtivas()]);
            } catch (Throwable $e) {
                Log::error('Evolução: falha ao refazer as checagens: ' . $e->getMessage());
                $c = null;
            }
            if (! $c || ! $c->successful()) {
                return response()->json(['message' => 'Não consegui refazer as checagens agora, então não aprovei. Tente de novo em instantes.'], 502);
            }
            if ($c->json('bloqueio')) {
                $motivos = collect($c->json('achados'))->where('gravidade', 'bloqueio')->pluck('mensagem')->implode('; ');

                return response()->json(['message' => 'As checagens fixas, refeitas agora, encontraram bloqueios: ' . $motivos], 422);
            }
        }

        $p->update([
            'status' => $d['aprovar'] ? 'aprovada' : 'reprovada', 'ativa' => (bool) $d['aprovar'],
            'decidida_por' => (string) ($request->attributes->get('usuario')?->nome ?? 'master'), 'decidida_em' => now(),
        ]);

        return response()->json($p->fresh()->paraFront());
    }

    public function desativar(string $codigo): JsonResponse
    {
        $p = EvolucaoProposta::where('codigo', $codigo)->where('status', 'aprovada')->where('ativa', true)->firstOrFail();
        $p->update(['ativa' => false]);

        return response()->json($p->fresh()->paraFront());
    }
}
