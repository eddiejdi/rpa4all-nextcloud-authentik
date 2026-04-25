<?php

declare(strict_types=1);

namespace OCA\RPA4AllAdminActions\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\JSONResponse;
use OCP\IGroupManager;
use OCP\IRequest;
use OCP\IUserSession;

class AdminController extends Controller {
    private const SCRIPTS_DIR = '/rpa4all_scripts';

    public function __construct(
        IRequest $request,
        private IUserSession $userSession,
        private IGroupManager $groupManager,
    ) {
        parent::__construct('rpa4all_admin_actions', $request);
    }

    /**
     * @NoAdminRequired
     * @NoCSRFRequired
     */
    public function relogin(string $userId): JSONResponse {
        $check = $this->requireAdmin();
        if ($check !== null) {
            return $check;
        }

        $safe = $this->sanitizeUserId($userId);
        if ($safe === '') {
            return new JSONResponse(['error' => 'userId inválido'], 400);
        }

        $script = self::SCRIPTS_DIR . '/relogin_user.py';
        $cmd = escapeshellcmd("python3 $script") . ' ' . escapeshellarg($safe) . ' 2>&1';
        exec($cmd, $output, $code);

        if ($code !== 0) {
            return new JSONResponse([
                'error'  => 'Falha ao executar re-login',
                'output' => implode("\n", $output),
            ], 500);
        }

        return new JSONResponse([
            'success' => true,
            'message' => "Re-login forçado para $safe",
            'output'  => implode("\n", $output),
        ]);
    }

    /**
     * @NoAdminRequired
     * @NoCSRFRequired
     */
    public function scan(string $userId): JSONResponse {
        $check = $this->requireAdmin();
        if ($check !== null) {
            return $check;
        }

        $safe = $this->sanitizeUserId($userId);
        if ($safe === '') {
            return new JSONResponse(['error' => 'userId inválido'], 400);
        }

        $script = self::SCRIPTS_DIR . '/force_sync_user.py';
        $cmd = escapeshellcmd("python3 $script") . ' ' . escapeshellarg($safe) . ' 2>&1';
        exec($cmd, $output, $code);

        if ($code !== 0) {
            return new JSONResponse([
                'error'  => 'Falha ao executar scan',
                'output' => implode("\n", $output),
            ], 500);
        }

        return new JSONResponse([
            'success' => true,
            'message' => "Force sync iniciado para $safe",
            'output'  => implode("\n", $output),
        ]);
    }

    private function requireAdmin(): ?JSONResponse {
        $user = $this->userSession->getUser();
        if ($user === null) {
            return new JSONResponse(['error' => 'Não autenticado'], 401);
        }
        if (!$this->groupManager->isInGroup($user->getUID(), 'admin')) {
            return new JSONResponse(['error' => 'Acesso restrito a administradores'], 403);
        }
        return null;
    }

    private function sanitizeUserId(string $userId): string {
        return preg_replace('/[^a-zA-Z0-9@._\-]/', '', $userId) ?? '';
    }
}
