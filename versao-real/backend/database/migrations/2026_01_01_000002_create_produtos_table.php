<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('produtos', function (Blueprint $t) {
            $t->id();
            $t->string('codigo')->unique();
            $t->string('nome');
            $t->string('categoria');
            $t->text('descricao')->nullable();
            $t->decimal('valor_diaria', 10, 2);
            $t->decimal('valor_reposicao', 10, 2)->default(0);
            $t->unsignedInteger('quantidade')->default(0);
            $t->boolean('ativo')->default(true);
            $t->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('produtos');
    }
};
