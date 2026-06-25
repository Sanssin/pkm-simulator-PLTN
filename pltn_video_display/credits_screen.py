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
        self.page_duration = 3.5  # seconds
        
        # Perfect Fourth fonts
        font_name = "inter"
        self.font_judul = pygame.font.SysFont(font_name, int(84 * app.scale))
        self.font_divisi = pygame.font.SysFont(font_name, int(63 * app.scale))
        self.font_nama = pygame.font.SysFont(font_name, int(48 * app.scale))
        
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
            # Create a solid surface matching the app's light theme
            # app.COLOR_BG is RGB (245, 248, 250).
            bg_color = self.app.COLOR_BG
            
            surface = pygame.Surface((self.width, self.height))
            surface.fill(bg_color)
            
            # Common Title for all pages
            title = self.font_judul.render("DAFTAR PENGEMBANG", True, self.app.COLOR_PRIMARY_BRIGHT)
            title_rect = title.get_rect(center=(self.width // 2, int(80 * self.app.scale)))
            surface.blit(title, title_rect)
            
            if i == 0:
                self._render_page_1_col(surface, group)
            else:
                self._render_page_2_cols(surface, group[0])
                
            self.pages.append(surface)
            
    def _render_page_1_col(self, surface, sections):
        y_offset = int(160 * self.app.scale)
        
        for section in sections:
            # Header
            header = self.font_divisi.render(section["section"], True, self.app.COLOR_PRIMARY)
            header_rect = header.get_rect(center=(self.width // 2, y_offset))
            surface.blit(header, header_rect)
            y_offset += int(52.5 * self.app.scale) + int(20 * self.app.scale)
            
            # Names
            for name in section["names"]:
                name_surf = self.font_nama.render(name, True, self.app.COLOR_TEXT)
                name_rect = name_surf.get_rect(center=(self.width // 2, y_offset))
                surface.blit(name_surf, name_rect)
                y_offset += int(32.8 * self.app.scale) + int(20 * self.app.scale)
            
            y_offset += int(20 * self.app.scale) # Spacing between sections

    def _render_page_2_cols(self, surface, section):
        y_offset = int(180 * self.app.scale)
        
        # Header (centered)
        header = self.font_divisi.render(section["section"], True, self.app.COLOR_PRIMARY)
        header_rect = header.get_rect(center=(self.width // 2, y_offset))
        surface.blit(header, header_rect)
        y_offset += int(52.5 * self.app.scale) + int(30 * self.app.scale)
        
        names = section["names"]
        
        # 2 columns
        mid = (len(names) + 1) // 2
        col1_names = names[:mid]
        col2_names = names[mid:]
        
        start_y = y_offset
        
        # Column 1
        x_col1 = self.width // 4
        y = start_y
        for name in col1_names:
            name_surf = self.font_nama.render(name, True, self.app.COLOR_TEXT)
            name_rect = name_surf.get_rect(center=(x_col1, y))
            surface.blit(name_surf, name_rect)
            y += int(32.8 * self.app.scale) + int(20 * self.app.scale)
            
        # Column 2
        x_col2 = (self.width * 3) // 4
        y = start_y
        for name in col2_names:
            name_surf = self.font_nama.render(name, True, self.app.COLOR_TEXT)
            name_rect = name_surf.get_rect(center=(x_col2, y))
            surface.blit(name_surf, name_rect)
            y += int(32.8 * self.app.scale) + int(20 * self.app.scale)

    def show(self):
        if not self.active:
            self.active = True
            self.current_page = 0
            self.last_advance_time = time.time()
        
    def hide(self):
        self.active = False
        
    def handle_tap(self):
        if not self.active:
            return False
            
        self.current_page += 1
        self.last_advance_time = time.time()
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
