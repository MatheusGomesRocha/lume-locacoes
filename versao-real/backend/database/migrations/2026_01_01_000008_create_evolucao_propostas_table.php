<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        // Consultas novas que os 3 Agents propõem para as perguntas sem resposta. A ia-api não guarda nada:
        // aqui ficam o relatório completo, a decisão do master e se a consulta está ativa no catálogo.
        Schema::create('evolucao_propostas', function (Blueprint $t) {
            $t->id();
            $t->string('codigo', 20)->unique();      // EV-0001
            $t->string('titulo', 200);
            $t->string('status', 12)->default('pendente'); // pendente | aprovada | reprovada
            $t->boolean('ativa')->default(false);
            $t->string('veredito', 30)->nullable();
            $t->json('relatorio');
            $t->string('decidida_por', 120)->nullable();
            $t->timestamp('decidida_em')->nullable();
            $t->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('evolucao_propostas');
    }
};
