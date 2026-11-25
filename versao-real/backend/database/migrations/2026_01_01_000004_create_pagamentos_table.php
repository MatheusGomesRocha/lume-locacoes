<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('pagamentos', function (Blueprint $t) {
            $t->id();
            $t->foreignId('orcamento_id')->constrained('orcamentos')->cascadeOnDelete();
            $t->decimal('valor', 12, 2);
            $t->date('vencimento');
            $t->date('pago_em')->nullable();
            $t->string('forma', 20)->nullable(); // pix, cartao, boleto, dinheiro
            $t->string('status', 20)->default('pendente'); // pendente, pago, cancelado
            $t->timestamps();
            $t->index(['status', 'vencimento']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('pagamentos');
    }
};
