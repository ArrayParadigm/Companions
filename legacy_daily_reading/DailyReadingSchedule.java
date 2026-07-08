import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import javax.swing.JFrame;
import javax.swing.JTabbedPane;
import javax.swing.JEditorPane;
import javax.swing.JScrollPane;

public class DailyReadingSchedule {

    public static void main(String[] args) {
        // Get today's date
        LocalDate today = LocalDate.now();
        int dayOfMonth = today.getDayOfMonth();

        // Determine which chapter to read for Proverbs and Acts
        int proverbChapter = dayOfMonth <= 31 ? dayOfMonth : dayOfMonth - 30;
        int actsChapter = dayOfMonth;

        // Set up the GUI
        JFrame frame = new JFrame("Daily Reading Schedule");
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        frame.setSize(800, 600);

        JTabbedPane tabbedPane = new JTabbedPane();
        frame.add(tabbedPane);

        // Create a tab for Proverbs
        JEditorPane proverbPane = new JEditorPane();
        String proverbText = getTextFromFile("kjv.txt", "Proverbs", proverbChapter);
        proverbPane.setContentType("text/html");
        proverbPane.setText("<html><body>" + proverbText + "</body></html>");
        JScrollPane proverbScrollPane = new JScrollPane(proverbPane);
        tabbedPane.addTab("Proverbs " + proverbChapter, proverbScrollPane);

        // Create tabs for Psalms
        int psalmStart = (dayOfMonth - 1) % 30 + 1;
        for (int i = 0; i < 5; i++) {
            int psalmChapter = psalmStart + i * 30;
            JEditorPane psalmPane = new JEditorPane();
            String psalmText = getTextFromFile("kjv.txt", "Psalms", psalmChapter);
            psalmPane.setContentType("text/html");
            psalmPane.setText("<html><body>" + psalmText + "</body></html>");
            JScrollPane psalmScrollPane = new JScrollPane(psalmPane);
            tabbedPane.addTab("Psalms " + psalmChapter, psalmScrollPane);
        }

        // Create a tab for Acts
        JEditorPane actsPane = new JEditorPane();
        String actsText = getTextFromFile("kjv.txt", "Acts", actsChapter);
        actsPane.setContentType("text/html");
        actsPane.setText("<html><body>" + actsText + "</body></html>");
        JScrollPane actsScrollPane = new JScrollPane(actsPane);
        tabbedPane.addTab("Acts " + actsChapter, actsScrollPane);

        // Display the GUI
        frame.setVisible(true);
    }

    private static String getTextFromFile(String filename, String book, int chapter) {
        try (BufferedReader reader = new BufferedReader(new FileReader(filename))) {
            String line;
            boolean foundBook = false;
            boolean foundChapter = false;
            StringBuilder textBuilder = new StringBuilder();

            while ((line = reader.readLine()) != null) {
                line = line.trim();

                if (line.startsWith("BOOK:") && line.split(":")[1].equalsIgnoreCase(book)) {
                    foundBook = true;
                    continue;
                }

                if (foundBook && line.startsWith(chapter + ":")) {
                    foundChapter = true;
                    continue;
                }

                if (foundChapter && (line.startsWith("BOOK:") || line.startsWith((chapter + 1) + ":"))) {
                    break;
                }

                if (foundChapter) {
                    textBuilder.append(line);
                    textBuilder.append("<br>");
                }
            }

            return textBuilder.toString();
        } catch (IOException e) {
            return
 "Error: Could not read file";
        }
    }
}
