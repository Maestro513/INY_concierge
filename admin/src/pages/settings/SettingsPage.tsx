import { useState } from 'react';
import {
  User, Mail, Lock, Shield, Bell, Moon, Sun,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';

export default function SettingsPage() {
  const [darkMode, setDarkMode] = useState(false);

  function toggleDark() {
    setDarkMode(!darkMode);
    document.documentElement.classList.toggle('dark');
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage your account and portal preferences
        </p>
      </div>

      {/* Profile */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <User className="h-4 w-4 text-muted-foreground" /> Profile
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                First Name
              </Label>
              <Input defaultValue="Admin" className="h-10 bg-muted/30 border-transparent" />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Last Name
              </Label>
              <Input defaultValue="User" className="h-10 bg-muted/30 border-transparent" />
            </div>
          </div>
          <div className="space-y-2">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Email
            </Label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input defaultValue="admin@iny.health" className="h-10 pl-10 bg-muted/30 border-transparent" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="secondary" className="text-[10px] font-semibold bg-primary/10 text-primary">
              <Shield className="mr-1 h-3 w-3" /> Super Admin
            </Badge>
            <span className="text-xs text-muted-foreground">Full access to all portal features</span>
          </div>
          <Button size="sm" className="text-xs">Save Changes</Button>
        </CardContent>
      </Card>

      {/* Security */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Lock className="h-4 w-4 text-muted-foreground" /> Security
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Current Password
            </Label>
            <Input type="password" placeholder="Enter current password" className="h-10 bg-muted/30 border-transparent" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                New Password
              </Label>
              <Input type="password" placeholder="New password" className="h-10 bg-muted/30 border-transparent" />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Confirm Password
              </Label>
              <Input type="password" placeholder="Confirm new password" className="h-10 bg-muted/30 border-transparent" />
            </div>
          </div>
          <Button size="sm" variant="outline" className="text-xs">Update Password</Button>
        </CardContent>
      </Card>

      {/* Preferences */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Bell className="h-4 w-4 text-muted-foreground" /> Preferences
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Dark Mode</p>
              <p className="text-xs text-muted-foreground">Toggle between light and dark theme</p>
            </div>
            <Button variant="outline" size="sm" className="h-8 text-xs gap-2" onClick={toggleDark}>
              {darkMode ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
              {darkMode ? 'Light' : 'Dark'}
            </Button>
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Email Notifications</p>
              <p className="text-xs text-muted-foreground">Get notified about system alerts and errors</p>
            </div>
            <Button variant="outline" size="sm" className="h-8 text-xs">
              Enabled
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
