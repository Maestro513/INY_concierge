import { Bell, Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { useAdminAuth } from '@/auth/AdminAuthProvider';

const ROLE_LABELS: Record<string, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  viewer: 'Viewer',
};

export default function Topbar() {
  const { user } = useAdminAuth();
  const initials = user
    ? `${user.first_name?.[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase() || 'AD'
    : 'AD';
  const displayName = user ? `${user.first_name} ${user.last_name}`.trim() || 'Admin' : 'Admin';
  const roleLabel = user ? ROLE_LABELS[user.role] ?? user.role : '';

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-card/80 px-6 backdrop-blur-sm">
      {/* Search */}
      <div className="relative w-80">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search members, plans..."
          className="h-9 pl-9 bg-muted/50 border-transparent focus:border-primary/30 focus:bg-card"
        />
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Notifications */}
        <button className="relative rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
          <Bell className="h-4.5 w-4.5" />
          <Badge className="absolute -right-0.5 -top-0.5 h-4.5 min-w-4.5 justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-primary-foreground">
            3
          </Badge>
        </button>

        {/* User */}
        <div className="flex items-center gap-3">
          <Avatar className="h-8 w-8 border-2 border-primary/20">
            <AvatarFallback className="bg-primary/10 text-xs font-bold text-primary">
              {initials}
            </AvatarFallback>
          </Avatar>
          <div className="hidden md:block">
            <p className="text-sm font-semibold leading-none">{displayName}</p>
            <p className="text-[11px] text-muted-foreground">{roleLabel}</p>
          </div>
        </div>
      </div>
    </header>
  );
}
