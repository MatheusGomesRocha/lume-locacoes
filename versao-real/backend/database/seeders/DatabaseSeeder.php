<?php

namespace Database\Seeders;

use App\Models\Cliente;
use App\Models\Orcamento;
use App\Models\Pagamento;
use App\Models\Produto;
use App\Services\OrcamentoService;
use Illuminate\Database\Seeder;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Carrega dados FICTÍCIOS de exemplo a partir de database/seeders/data/seed.json.
 * O mesmo arquivo alimenta a versão de demonstração (GitHub Pages), então as duas partem dos mesmos dados.
 * Datas no arquivo são deslocamentos em dias a partir de hoje.
 */
class DatabaseSeeder extends Seeder
{
    public function run(): void
    {
        $dados = json_decode(file_get_contents(database_path('seeders/data/seed.json')), true, 512, JSON_THROW_ON_ERROR);
        $hoje = Carbon::today();

        DB::transaction(function () use ($dados, $hoje) {
            foreach ($dados['clientes'] as $cliente) {
                Cliente::forceCreate($cliente);
            }
            foreach ($dados['produtos'] as $produto) {
                Produto::forceCreate($produto);
            }

            $precos = collect($dados['produtos'])->pluck('valor_diaria', 'id');
            $sequencia = [];
            $totais = [];

            foreach ($dados['orcamentos'] as $o) {
                $criado = $hoje->copy()->addDays($o['criado_dias']);
                $retirada = $hoje->copy()->addDays($o['retirada_dias'])->toDateString();
                $devolucao = $hoje->copy()->addDays($o['devolucao_dias'])->toDateString();
                $itens = array_map(fn ($i) => [
                    'produto_id' => $i['produto_id'],
                    'quantidade' => $i['quantidade'],
                    'valor_diaria' => (float) $precos[$i['produto_id']],
                ], $o['itens']);

                $sequencia[$criado->year] = ($sequencia[$criado->year] ?? 0) + 1;
                $total = OrcamentoService::calcularTotal($itens, OrcamentoService::diarias($retirada, $devolucao), $o['desconto']);
                $totais[$o['id']] = $total;

                $orcamento = Orcamento::forceCreate([
                    'id' => $o['id'],
                    'numero' => sprintf('%d/%04d', $criado->year, $sequencia[$criado->year]),
                    'cliente_id' => $o['cliente_id'],
                    'evento' => $o['evento'],
                    'data_retirada' => $retirada,
                    'data_devolucao' => $devolucao,
                    'status' => $o['status'],
                    'desconto' => $o['desconto'],
                    'total' => $total,
                    'observacoes' => $o['observacoes'] ?: null,
                    'created_at' => $criado,
                    'updated_at' => $criado,
                ]);
                $orcamento->itens()->createMany($itens);
            }

            foreach ($dados['pagamentos'] as $p) {
                $pagoEm = $p['pago_dias'] === null ? null : $hoje->copy()->addDays($p['pago_dias'])->toDateString();
                Pagamento::create([
                    'orcamento_id' => $p['orcamento_id'],
                    'valor' => $totais[$p['orcamento_id']],
                    'vencimento' => $hoje->copy()->addDays($p['vencimento_dias'])->toDateString(),
                    'pago_em' => $pagoEm,
                    'forma' => $p['forma'],
                    'status' => $pagoEm === null ? Pagamento::PENDENTE : Pagamento::PAGO,
                ]);
            }
        });
    }
}
