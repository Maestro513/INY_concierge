import { useState } from 'react';
import {
  User, Mail, Lock, Shield, Bell, Moon, Sun, Check, AlertCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { useAdminAuth } from '@/auth/AdminAuthProvider';
import client from '@/api/client';
import { ENDPOINTS } from '@/config/api';

export default function SettingsPage() {
  const { user } = useAdminAuth();
  const [darkMode, setDarkMode] = useState(false);

  // Profile state
  const [firstName, setFirstName] = useState(user?.first_name || '');
  const [lastName, setLastName] = useState(user?.last_name || '');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [profileError, setProfileError] = useState('');

  // Password state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const [passwordError, setPasswordError] = useState('');

  function toggleDark() {
    setDarkMode(!darkMode);
    document.documentElement.classList.toggle('dark');
  }

  async function handleProfileSave() {
    if (!user) return;
    setProfileSaving(true);
    setProfileError('');
    setProfileSuccess(false);
    try {
      await client.patch(ENDPOINTS.ADMIN_USER(user.id), {
        first_name: firstName,
        last_name: lastName,
      });
      setProfileSuccess(true);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } };
      if (axiosErr.response?.status === 403) {
        setProfileError('Only super admins can update profiles.');
      } else {
        setProfileError(axiosErr.response?.data?.detail || 'Failed to update profile.');
      }
    } finally {
      setProfileSaving(false);
    }
  }

  async function handlePasswordSave() {
    if (!user) return;
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match.');
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError('Password must be at least 8 characters.');
      return;
    }
    setPasswordSaving(true);
    setPasswordError('');
    setPasswordSuccess(false);
    try {
      await client.patch(ENDPOINTS.ADMIN_USER(user.id), {
        password: newPassword,
      });
      setPasswordSuccess(true);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } };
      if (axiosErr.response?.status === 422) {
        setPasswordError('Password must include uppercase, lowercase, digit, and special character.');
      } else if (axiosErr.response?.status === 403) {
        setPasswordError('Only super admins can change passwords.');
      } else {
        setPasswordError(axiosErr.response?.data?.detail || 'Failed to update password.');
      }
    } finally {
      setPasswordSaving(false);
    }
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
              <Input
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                className="h-10 bg-muted/30 border-transparent"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Last Name
              </Label>
              <Input
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                className="h-10 bg-muted/30 border-transparent"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Email
            </Label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={user?.email || ''}
                disabled
                className="h-10 pl-10 bg-muted/30 border-transparent opacity-60"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="secondary" className="text-[10px] font-semibold bg-primary/10 text-primary">
              <Shield className="mr-1 h-3 w-3" /> {user?.role?.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()) || 'Admin'}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {user?.role === 'super_admin' ? 'Full access to all portal features' :
               user?.role === 'admin' ? 'Can manage members and plans' :
               'View-only access'}
            </span>
          </div>

          {profileError && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span className="text-xs">{profileError}</span>
            </div>
          )}
          {profileSuccess && (
            <div className="flex items-center gap-1.5 text-success">
              <Check className="h-3.5 w-3.5" />
              <span className="text-xs font-medium">Profile updated</span>
            </div>
          )}

          <Button
            size="sm"
            className="text-xs"
            onClick={handleProfileSave}
            disabled={profileSaving || !firstName || !lastName}
          >
            {profileSaving ? (
              <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Saving...</>
            ) : (
              'Save Changes'
            )}
          </Button>
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
            <Input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Enter current password"
              className="h-10 bg-muted/30 border-transparent"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                New Password
              </Label>
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="New password"
                className="h-10 bg-muted/30 border-transparent"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Confirm Password
              </Label>
              <Input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm new password"
                className="h-10 bg-muted/30 border-transparent"
              />
            </div>
          </div>

          {passwordError && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span className="text-xs">{passwordError}</span>
            </div>
          )}
          {passwordSuccess && (
            <div className="flex items-center gap-1.5 text-success">
              <Check className="h-3.5 w-3.5" />
              <span className="text-xs font-medium">Password updated</span>
            </div>
          )}

          <Button
            size="sm"
            variant="outline"
            className="text-xs"
            onClick={handlePasswordSave}
            disabled={passwordSaving || !newPassword || !confirmPassword}
          >
            {passwordSaving ? (
              <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Updating...</>
            ) : (
              'Update Password'
            )}
          </Button>
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
