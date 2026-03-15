import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare, Search, User, Clock, ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import client from '@/api/client';
import { ENDPOINTS } from '@/config/api';

interface Conversation {
  phone_hash: string;
  phone_last4: string;
  member_name: string;
  last_message_at: string;
  last_message_preview: string;
  total_messages: number;
  unread_from_member: number;
}

export default function MessagesInboxPage() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadInbox();
  }, []);

  async function loadInbox() {
    try {
      const res = await client.get(ENDPOINTS.MESSAGES_INBOX);
      setConversations(res.data?.conversations || []);
    } catch {
      // Handle error silently
    } finally {
      setLoading(false);
    }
  }

  const filtered = conversations.filter((c) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      c.member_name?.toLowerCase().includes(q) ||
      c.phone_last4?.includes(q)
    );
  });

  function formatTime(dateStr: string) {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'Z');
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHrs = Math.floor(diffMin / 60);
    if (diffHrs < 24) return `${diffHrs}h ago`;
    const diffDays = Math.floor(diffHrs / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Messages</h1>
        <p className="text-sm text-muted-foreground mt-1">
          All member conversations. Click a conversation to view and reply on the member detail page.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="border-border/50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <MessageSquare className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="text-2xl font-bold">{conversations.length}</p>
                <p className="text-xs text-muted-foreground">Total Conversations</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-chart-4/10 flex items-center justify-center">
                <MessageSquare className="h-5 w-5 text-chart-4" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {conversations.filter((c) => c.unread_from_member > 0).length}
                </p>
                <p className="text-xs text-muted-foreground">With Unread Messages</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-success/10 flex items-center justify-center">
                <Clock className="h-5 w-5 text-success" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {conversations.reduce((sum, c) => sum + c.total_messages, 0)}
                </p>
                <p className="text-xs text-muted-foreground">Total Messages</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Inbox */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold">Inbox</CardTitle>
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name or phone..."
                className="pl-9 h-8 text-xs"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12">
              <MessageSquare className="mx-auto h-10 w-10 text-muted-foreground/40" />
              <p className="mt-3 text-sm text-muted-foreground">
                {search ? 'No conversations match your search' : 'No conversations yet'}
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {filtered.map((conv) => (
                <button
                  key={conv.phone_hash}
                  className="w-full flex items-center gap-4 rounded-lg border border-transparent p-3 text-left transition-colors hover:bg-muted/50 hover:border-border/50"
                  onClick={() => {
                    // Navigate to member detail with phone_last4
                    // The phone is stored hashed; the inbox endpoint returns phone for navigation
                    if (conv.phone_last4) {
                      navigate(`/admin/members/${conv.phone_last4}`, { state: { tab: 'messaging' } });
                    }
                  }}
                >
                  <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <User className="h-5 w-5 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold truncate">
                        {conv.member_name || `Member ...${conv.phone_last4}`}
                      </p>
                      <span className="text-[10px] text-muted-foreground shrink-0 ml-2">
                        {formatTime(conv.last_message_at)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between mt-0.5">
                      <p className="text-xs text-muted-foreground truncate">
                        {conv.last_message_preview || `${conv.total_messages} messages`}
                      </p>
                      {conv.unread_from_member > 0 && (
                        <Badge className="ml-2 h-5 min-w-[20px] flex items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground shrink-0">
                          {conv.unread_from_member}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground/50 shrink-0" />
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
