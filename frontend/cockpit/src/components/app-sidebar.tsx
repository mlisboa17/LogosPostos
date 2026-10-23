"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NavSecondary } from "@/components/nav-secondary";
import { NavUser } from "@/components/nav-user";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarGroup,
  SidebarGroupLabel,
} from "@/components/ui/sidebar";
import {
  BarChart3Icon,
  ClipboardCheckIcon,
  FuelIcon,
  LayoutGridIcon,
  PackageIcon,
  Settings2Icon,
  ShoppingCartIcon,
  CheckSquareIcon,
} from "lucide-react";

const navMain = [
  { title: "Painel", url: "/dashboard", icon: LayoutGridIcon },
  { title: "Classificação", url: "/revisao", icon: CheckSquareIcon },
  { title: "Abastecimento", url: "/abastecimento", icon: FuelIcon },
  { title: "Vendas", url: "/vendas", icon: ShoppingCartIcon },
  { title: "Produtos", url: "/produtos", icon: PackageIcon },
  { title: "Auditoria", url: "/auditoria", icon: ClipboardCheckIcon },
];

const navSecondary = [
  { title: "Configurações", url: "#", icon: <Settings2Icon className="size-4" /> },
];

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader className="border-b border-sidebar-border p-4">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              className="hover:bg-sidebar-accent"
              render={<Link href="/dashboard" />}
            >
              <div className="flex size-9 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <BarChart3Icon className="size-5" />
              </div>
              <div className="grid flex-1 text-left leading-tight">
                <span className="truncate text-sm font-bold">Logos Space</span>
                <span className="truncate text-xs text-sidebar-foreground/70">
                  WebPosto · Posto VIP
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Menu principal</SidebarGroupLabel>
          <SidebarMenu>
            {navMain.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.url;
              return (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton
                    tooltip={item.title}
                    isActive={active}
                    className={
                      active
                        ? "bg-sidebar-primary text-sidebar-primary-foreground font-medium"
                        : undefined
                    }
                    render={<Link href={item.url} />}
                  >
                    <Icon />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
        <NavSecondary items={navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter className="border-t border-sidebar-border">
        <NavUser
          user={{
            name: "Grupo Lisboa",
            email: "mlisboa17@gmail.com",
            avatar: "",
          }}
        />
      </SidebarFooter>
    </Sidebar>
  );
}
