<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('grupos', function (Blueprint $t) {
            $t->id();
            $t->string('nome')->unique();
            $t->string('descricao')->nullable();
            $t->json('permissoes');
            $t->boolean('sistema')->default(false); // o grupo do master: não pode ser alterado nem excluído
            $t->timestamps();
        });

        Schema::create('usuarios', function (Blueprint $t) {
            $t->id();
            $t->string('nome');
            $t->string('email')->unique();
            $t->string('senha');
            $t->string('papel', 10)->default('usuario'); // master | admin | usuario
            $t->foreignId('grupo_id')->constrained('grupos'); // obrigatório: sem grupo não há acesso
            $t->boolean('ativo')->default(true);
            $t->timestamps();
        });

        // Só o hash do token fica no banco: quem ler a tabela não consegue usar as sessões.
        Schema::create('tokens_acesso', function (Blueprint $t) {
            $t->id();
            $t->foreignId('usuario_id')->constrained('usuarios')->cascadeOnDelete();
            $t->string('token_hash', 64)->unique();
            $t->timestamp('expira_em');
            $t->timestamp('usado_em')->nullable();
            $t->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('tokens_acesso');
        Schema::dropIfExists('usuarios');
        Schema::dropIfExists('grupos');
    }
};
