import pygame
import time
from credits_data import CREDITS

class CreditsScreen:
    def __init__(self, app):
        self.app = app
        self.width = app.width
        self.height = app.height
        
        self.active = False
        self.current_page = 0
        self.last_advance_time = 0
        self.page_duration = 5.0  # seconds
        
        self.pages = []
        self._pre_render_pages()
        
    def _pre_render_pages(self):
        # Create 3 pages based on the prompt grouping
        # Page 1: 3 sections (1 col)
        # Page 2: 1 section (2 cols)
        # Page 3: 1 section (2 cols)
        
        page_groups = [
            [CREDITS[0], CREDITS[1], CREDITS[2]],  # Page 1
            [CREDITS[3]],                          # Page 2
            [CREDITS[4]]                           # Page 3
        ]
        
        for i, group in enumerate(page_groups):
            # Create a solid background
            bg_color = self.app.COLOR_BG
            
            surface = pygame.Surface((self.width, self.height))
            surface.fill(bg_color)
            
            # Draw Logos
            margin_x = int(50 * self.app.scale)
            header_y = int(40 * self.app.scale)
            if hasattr(self.app, 'logo_brin') and self.app.logo_brin:
                surface.blit(self.app.logo_brin, (margin_x, header_y))
            if hasattr(self.app, 'logo_poltek') and self.app.logo_poltek:
                logo_x = self.width - getattr(self.app, 'logo_size_large', (150,150))[0] - margin_x
                surface.blit(self.app.logo_poltek, (logo_x, header_y))
            
            # Common Title for all pages
            title = self.app.font_display.render("DAFTAR PENGEMBANG", True, self.app.COLOR_PRIMARY_BRIGHT)
            title_rect = title.get_rect(center=(self.width // 2, int(100 * self.app.scale)))
            surface.blit(title, title_rect)
            
            self._render_page(surface, group)
            self.pages.append(surface)
            
    def _render_page(self, surface, sections):
        # Start a bit higher if we have multiple sections to fit them
        y_offset = int(220 * self.app.scale) if len(sections) > 1 else int(250 * self.app.scale)
        for section in sections:
            y_offset = self._render_section(surface, section, y_offset)
            
    def _render_section(self, surface, section, start_y):
        y_offset = start_y
        
        # Header
        header = self.app.font_idle_sub.render(section["section"], True, self.app.COLOR_PRIMARY)
        header_rect = header.get_rect(center=(self.width // 2, y_offset))
        surface.blit(header, header_rect)
        y_offset += int(70 * self.app.scale)
        
        names = section["names"]
        
        # Choose layout based on number of names
        if len(names) <= 2:
            # 1 Column
            for name in names:
                name_surf = self.app.font_idle_desc.render(name, True, self.app.COLOR_TEXT)
                name_rect = name_surf.get_rect(center=(self.width // 2, y_offset))
                surface.blit(name_surf, name_rect)
                y_offset += int(55 * self.app.scale)
        elif len(names) < 12:
            # 2 Columns
            mid = (len(names) + 1) // 2
            col1 = names[:mid]
            col2 = names[mid:]
            
            x1 = self.width // 3
            x2 = self.width * 2 // 3
            
            y_col1 = y_offset
            for name in col1:
                name_surf = self.app.font_idle_desc.render(name, True, self.app.COLOR_TEXT)
                name_rect = name_surf.get_rect(center=(x1, y_col1))
                surface.blit(name_surf, name_rect)
                y_col1 += int(55 * self.app.scale)
                
            y_col2 = y_offset
            for name in col2:
                name_surf = self.app.font_idle_desc.render(name, True, self.app.COLOR_TEXT)
                name_rect = name_surf.get_rect(center=(x2, y_col2))
                surface.blit(name_surf, name_rect)
                y_col2 += int(55 * self.app.scale)
                
            y_offset = max(y_col1, y_col2)
        else:
            # 3 Columns
            col_len = (len(names) + 2) // 3
            col1 = names[:col_len]
            col2 = names[col_len:col_len*2]
            col3 = names[col_len*2:]
            
            x1 = self.width // 6
            x2 = self.width // 2
            x3 = self.width * 5 // 6
            
            y_col1 = y_offset
            for name in col1:
                name_surf = self.app.font_idle_desc.render(name, True, self.app.COLOR_TEXT)
                name_rect = name_surf.get_rect(center=(x1, y_col1))
                surface.blit(name_surf, name_rect)
                y_col1 += int(55 * self.app.scale)
                
            y_col2 = y_offset
            for name in col2:
                name_surf = self.app.font_idle_desc.render(name, True, self.app.COLOR_TEXT)
                name_rect = name_surf.get_rect(center=(x2, y_col2))
                surface.blit(name_surf, name_rect)
                y_col2 += int(55 * self.app.scale)
                
            y_col3 = y_offset
            for name in col3:
                name_surf = self.app.font_idle_desc.render(name, True, self.app.COLOR_TEXT)
                name_rect = name_surf.get_rect(center=(x3, y_col3))
                surface.blit(name_surf, name_rect)
                y_col3 += int(55 * self.app.scale)
                
            y_offset = max(y_col1, y_col2, y_col3)
            
        return y_offset + int(60 * self.app.scale) # Spacing before next section

    def show(self):
        if not self.active:
            self.active = True
            self.current_page = 0
            self.last_advance_time = time.time()
            self._last_tap_time = time.time() + 1.0  # Ignore taps for 1s after showing
        
    def hide(self):
        self.active = False
        
    def handle_tap(self):
        if not self.active:
            return False
            
        now = time.time()
        # Debounce taps to prevent rapid double/triple firing from touch drivers
        if now - getattr(self, '_last_tap_time', 0) < 0.5:
            return True
            
        self._last_tap_time = now
        self.current_page += 1
        self.last_advance_time = now
        if self.current_page >= len(self.pages):
            self.hide()
        return True
        
    def update(self):
        if not self.active:
            return
            
        now = time.time()
        if now - self.last_advance_time >= self.page_duration:
            self.current_page += 1
            self.last_advance_time = now
            if self.current_page >= len(self.pages):
                self.hide()
                
    def draw(self, screen):
        if not self.active or self.current_page >= len(self.pages):
            return
        # Blit the current page over the screen
        screen.blit(self.pages[self.current_page], (0, 0))
