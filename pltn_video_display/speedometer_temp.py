    def draw_speedometer_gauge(self, state: Dict, content_y_start: int, col_start: int, col_width: int):
        """Draw speedometer-style power gauge in right column
        
        Args:
            state: Current simulation state
            content_y_start: Y position where content starts
            col_start: X position of right column start
            col_width: Width of right column
        """
        import math
        
        # Get thermal power from state (in kW)
        thermal_kw = state.get("thermal_kw", 0.0)
        thermal_mw = thermal_kw / 1000.0  # Convert kW to MW
        
        # Speedometer dimensions (scaled for 1366px and 4K)
        diameter = int(320 * self.scale)  # 320px for 1366px, 600px for 4K
        radius = diameter // 2
        arc_thickness = int(40 * self.scale)
        
        # Center position in right column
        center_x = col_start + col_width // 2
        center_y = content_y_start + int(self.height * 0.35)  # Vertically centered
        
        # Title: "DAYA OUTPUT"
        title_text = self.font_display.render("DAYA OUTPUT", True, self.COLOR_TEXT)
        title_rect = title_text.get_rect(center=(center_x, center_y - radius - int(60 * self.scale)))
        self.screen.blit(title_text, title_rect)
        
        # === DRAW ARC BACKGROUND (180° semicircle) ===
        # Arc from 180° (left) to 0° (right), bottom half of circle
        arc_rect = pygame.Rect(center_x - radius, center_y - radius, diameter, diameter)
        
        # Background arc (gray)
        pygame.draw.arc(self.screen, self.COLOR_TEXT_SECONDARY, arc_rect,
                       math.pi, 2 * math.pi, arc_thickness)
        
        # === DRAW COLORED ARC FILL ===
        # Calculate power percentage (0-100%)
        MAX_THERMAL_MW = 30.0
        power_percentage = min((thermal_mw / MAX_THERMAL_MW) * 100.0, 100.0)
        
        # Determine arc color based on power level
        if power_percentage < 30:
            arc_color = self.COLOR_TEXT_SECONDARY  # Gray - Low
        elif power_percentage < 70:
            arc_color = self.COLOR_WARNING  # Yellow - Medium
        else:
            arc_color = self.COLOR_SUCCESS  # Green - High
        
        # Draw filled arc (from left, proportional to power)
        # Angle: 180° (π) to 180° + (percentage * 180°)
        if power_percentage > 0:
            end_angle = math.pi + (power_percentage / 100.0) * math.pi
            pygame.draw.arc(self.screen, arc_color, arc_rect,
                           math.pi, end_angle, arc_thickness)
        
        # === DRAW SCALE MARKERS ===
        # Markers at 0, 10, 20, 30 MW
        marker_length = int(15 * self.scale)
        marker_thickness = max(int(3 * self.scale), 2)
        
        for mw_value in [0, 10, 20, 30]:
            # Calculate angle for this MW value
            angle = math.pi + (mw_value / MAX_THERMAL_MW) * math.pi
            
            # Outer point (on arc)
            outer_x = center_x + int((radius - arc_thickness // 2) * math.cos(angle))
            outer_y = center_y + int((radius - arc_thickness // 2) * math.sin(angle))
            
            # Inner point (marker line)
            inner_x = center_x + int((radius - arc_thickness // 2 - marker_length) * math.cos(angle))
            inner_y = center_y + int((radius - arc_thickness // 2 - marker_length) * math.sin(angle))
            
            # Draw marker line
            pygame.draw.line(self.screen, self.COLOR_TEXT, 
                           (outer_x, outer_y), (inner_x, inner_y), marker_thickness)
            
            # Draw MW label
            label_text = self.font_body.render(f"{mw_value}", True, self.COLOR_TEXT_SECONDARY)
            label_x = center_x + int((radius + int(25 * self.scale)) * math.cos(angle))
            label_y = center_y + int((radius + int(25 * self.scale)) * math.sin(angle))
            label_rect = label_text.get_rect(center=(label_x, label_y))
            self.screen.blit(label_text, label_rect)
        
        # === DRAW NEEDLE POINTER ===
        # Needle angle based on current power
        needle_angle = math.pi + (power_percentage / 100.0) * math.pi
        needle_length = radius - arc_thickness // 2 - int(10 * self.scale)
        needle_thickness = max(int(4 * self.scale), 3)
        
        # Needle endpoint
        needle_x = center_x + int(needle_length * math.cos(needle_angle))
        needle_y = center_y + int(needle_length * math.sin(needle_angle))
        
        # Draw needle (from center to endpoint)
        pygame.draw.line(self.screen, self.COLOR_TEXT, 
                        (center_x, center_y), (needle_x, needle_y), needle_thickness)
        
        # Draw center circle (needle pivot)
        center_circle_radius = int(8 * self.scale)
        pygame.draw.circle(self.screen, self.COLOR_TEXT, (center_x, center_y), center_circle_radius)
        
        # === DRAW MW VALUE (center display) ===
        mw_text = f"{thermal_mw:.1f} MW"
        mw_surface = self.font_display.render(mw_text, True, self.COLOR_PRIMARY_BRIGHT)
        mw_rect = mw_surface.get_rect(center=(center_x, center_y + int(60 * self.scale)))
        self.screen.blit(mw_surface, mw_rect)
        
        # === DRAW LABEL ===
        label_text = "Daya Termal"
        label_surface = self.font_medium.render(label_text, True, self.COLOR_TEXT_SECONDARY)
        label_rect = label_surface.get_rect(center=(center_x, center_y + int(100 * self.scale)))
        self.screen.blit(label_surface, label_rect)
