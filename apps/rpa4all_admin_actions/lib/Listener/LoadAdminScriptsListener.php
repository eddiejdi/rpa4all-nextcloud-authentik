<?php

declare(strict_types=1);

namespace OCA\RPA4AllAdminActions\Listener;

use OCP\AppFramework\Http\Events\BeforeTemplateRenderedEvent;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\Util;

class LoadAdminScriptsListener implements IEventListener {
    public function handle(Event $event): void {
        if (!($event instanceof BeforeTemplateRenderedEvent)) {
            return;
        }

        $uri = $_SERVER['REQUEST_URI'] ?? '';
        if (str_contains($uri, '/settings/users')) {
            Util::addScript('rpa4all_admin_actions', 'admin-users');
            Util::addStyle('rpa4all_admin_actions', 'admin-users');
        }
    }
}
