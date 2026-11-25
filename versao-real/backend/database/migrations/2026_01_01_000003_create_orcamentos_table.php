<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('orcamentos', function (Blueprint $t) {
            $t->id();
            $t->string('numero')->unique(); // AAAA/NNNN
            $t->foreignId('cliente_id')->constrained('clientes')->restrictOnDelete();
            $t->string('evento');
            $t->date('data_retirada');
            $t->date('data_devolucao');
            $t->string('status', 20)->default('rascunho');
            $t->decimal('desconto', 10, 2)->default(0);
            $t->decimal('total', 12, 2)->default(0);
            $t->text('observacoes')->nullable();
            $t->timestamps();
            $t->index(['status', 'data_retirada']);
        });

        Schema::create('orcamento_itens', function (Blueprint $t) {
            $t->id();
            $t->foreignId('orcamento_id')->constrained('orcamentos')->cascadeOnDelete();
            $t->foreignId('produto_id')->constrained('produtos')->restrictOnDelete();
            $t->unsignedInteger('quantidade');
            $t->decimal('valor_diaria', 10, 2); // valor congelado no momento em que o item entrou
            $t->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('orcamento_itens');
        Schema::dropIfExists('orcamentos');
    }
};
