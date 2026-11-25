<?php

namespace Tests\Unit;

use App\Models\Orcamento;
use App\Services\OrcamentoService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Tests\Concerns\CriaDados;
use Tests\TestCase;

class OrcamentoServiceTest extends TestCase
{
    use CriaDados;
    use RefreshDatabase;

    public function test_diarias_conta_os_dias_entre_retirada_e_devolucao(): void
    {
        $this->assertSame(2, OrcamentoService::diarias('2026-12-10', '2026-12-12'));
        $this->assertSame(3, OrcamentoService::diarias('2026-01-30', '2026-02-02'));
    }

    public function test_diarias_tem_minimo_de_uma(): void
    {
        $this->assertSame(1, OrcamentoService::diarias('2026-12-10', '2026-12-10'));
        $this->assertSame(1, OrcamentoService::diarias('2026-12-12', '2026-12-10'));
        $this->assertSame(1, OrcamentoService::diarias(null, null));
    }

    public function test_calcular_total_multiplica_itens_pelas_diarias(): void
    {
        $itens = [['quantidade' => 2, 'valor_diaria' => 100], ['quantidade' => 1, 'valor_diaria' => 50]];

        $this->assertSame(750.0, OrcamentoService::calcularTotal($itens, 3));
    }

    public function test_calcular_total_subtrai_o_desconto_depois_das_diarias(): void
    {
        $itens = [['quantidade' => 2, 'valor_diaria' => 100], ['quantidade' => 1, 'valor_diaria' => 50]];

        $this->assertSame(650.0, OrcamentoService::calcularTotal($itens, 3, 100));
    }

    public function test_calcular_total_nunca_fica_negativo(): void
    {
        $this->assertSame(0.0, OrcamentoService::calcularTotal([['quantidade' => 1, 'valor_diaria' => 50]], 1, 999));
        $this->assertSame(0.0, OrcamentoService::calcularTotal([], 2, 0));
    }

    public function test_calcular_total_arredonda_em_centavos(): void
    {
        $this->assertSame(99.99, OrcamentoService::calcularTotal([['quantidade' => 3, 'valor_diaria' => 33.33]], 1));
    }

    public function test_proximo_numero_comeca_em_0001_no_ano(): void
    {
        $this->assertSame('2026/0001', OrcamentoService::proximoNumero(Carbon::parse('2026-05-01')));
    }

    public function test_proximo_numero_soma_um_ao_maior_do_ano(): void
    {
        $this->orcamento(dados: ['numero' => '2026/0001']);
        $this->orcamento(dados: ['numero' => '2026/0007']);

        $this->assertSame('2026/0008', OrcamentoService::proximoNumero(Carbon::parse('2026-05-01')));
    }

    public function test_proximo_numero_reinicia_a_cada_ano(): void
    {
        $this->orcamento(dados: ['numero' => '2026/0042']);

        $this->assertSame('2027/0001', OrcamentoService::proximoNumero(Carbon::parse('2027-01-02')));
    }

    public function test_proximo_numero_nao_repete_depois_de_excluir_um_antigo(): void
    {
        $primeiro = $this->orcamento(dados: ['numero' => '2026/0001']);
        $this->orcamento(dados: ['numero' => '2026/0002']);
        $primeiro->delete();

        $this->assertSame('2026/0003', OrcamentoService::proximoNumero(Carbon::parse('2026-05-01')));
    }

    public function test_faltas_considera_so_orcamentos_aprovados_que_se_sobrepoem(): void
    {
        $produto = $this->produto(['quantidade' => 5]);
        $this->orcamento('aprovado', '2026-12-10', '2026-12-12', [[$produto, 4]]);
        $this->orcamento('rascunho', '2026-12-10', '2026-12-12', [[$produto, 5]]);   // rascunho não segura estoque
        $this->orcamento('finalizado', '2026-12-10', '2026-12-12', [[$produto, 5]]); // finalizado já devolveu
        $novo = $this->orcamento('rascunho', '2026-12-11', '2026-12-13', [[$produto, 2]]);

        $faltas = (new OrcamentoService())->faltas($novo);

        $this->assertCount(1, $faltas);
        $this->assertSame(['solicitado' => 2, 'disponivel' => 1], ['solicitado' => $faltas[0]['solicitado'], 'disponivel' => $faltas[0]['disponivel']]);
    }

    public function test_faltas_ignora_o_proprio_orcamento_e_periodos_que_nao_se_tocam(): void
    {
        $produto = $this->produto(['quantidade' => 5]);
        $this->orcamento('aprovado', '2026-12-01', '2026-12-05', [[$produto, 5]]); // termina antes
        $orcamento = $this->orcamento('aprovado', '2026-12-10', '2026-12-12', [[$produto, 5]]);

        $this->assertSame([], (new OrcamentoService())->faltas($orcamento));
    }

    public function test_faltas_trata_as_datas_de_borda_como_sobreposicao(): void
    {
        $produto = $this->produto(['quantidade' => 3]);
        $this->orcamento('aprovado', '2026-12-10', '2026-12-14', [[$produto, 3]]);
        $novo = $this->orcamento('rascunho', '2026-12-14', '2026-12-16', [[$produto, 1]]); // começa no dia em que o outro termina

        $this->assertCount(1, (new OrcamentoService())->faltas($novo));
    }

    public function test_status_possiveis(): void
    {
        $this->assertSame(['rascunho', 'enviado', 'aprovado', 'finalizado', 'cancelado'], Orcamento::STATUS);
    }
}
