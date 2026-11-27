<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        // Agent 4 (Aprovador): o parecer dele sobre cada proposta e, se o modo automático estiver ligado, a marca de que ele aprovou.
        Schema::table('evolucao_propostas', function (Blueprint $t) {
            $t->json('revisao')->nullable();                 // decisão, condições C1..C5, risco, reprodução e parecer do modelo
            $t->timestamp('revisao_em')->nullable();
            $t->boolean('auto_aprovada')->default(false);    // true só quando o Agent 4 aprovou sozinho (modo automático)
            $t->boolean('amostra')->default(false);          // aprovação automática sorteada para o master conferir
            $t->string('conferida_por', 120)->nullable();
        });
    }

    public function down(): void
    {
        Schema::table('evolucao_propostas', function (Blueprint $t) {
            $t->dropColumn(['revisao', 'revisao_em', 'auto_aprovada', 'amostra', 'conferida_por']);
        });
    }
};
