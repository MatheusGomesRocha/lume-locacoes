<?php

namespace App\Http\Controllers;

use App\Services\DashboardService;

class DashboardController extends Controller
{
    public function __invoke(DashboardService $servico): array
    {
        return $servico->resumo();
    }
}
