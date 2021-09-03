import sys

from email.mime.text import MIMEText

from twisted.internet import reactor
from twisted.mail.smtp import sendmail
from twisted.python import log
from tkinter.filedialog import askopenfilename

log.startLogging(sys.stdout)

# Truzz Blogg | Python + Tkinter | How to create a GUI
# How to create a registration form using Python + Tkinter

# Let's import tkinter
from tkinter import *

# import tkinter as tk

# Manipulate data from registration fields
def send_data():
    from_info = _from.get()
    to_info = to.get()
    subject_info = subject.get()
    message_info = str(message.get())
    print(from_info, "\t", to_info, "\t", subject_info, "\t", message_info)
    host = "localhost"
    if "," in  to_info:
        recipients = to_info.split(",")
    else:
        recipients = to_info
    msg = MIMEText(message_info)
    msg["Subject"] = subject_info
    msg["From"] = from_info
    msg["To"] = ", ".join(recipients)
    deferred = sendmail(host, from_info, recipients, msg, port=2525)
    deferred.addBoth(lambda result: reactor.stop())

    reactor.run()

    #  Delete data from previous event
    from_entry.delete(0, END)
    subject_entry.delete(0, END)
    message_entry.delete(0, END)


# Create new instance - Class Tk()
mywindow = Tk()
mywindow.geometry("375x475")
mywindow.title("SMPT Client")
mywindow.resizable(False, False)
mywindow.config(background="#213141")
main_title = Label(text="Python Twisted - SPMT Client", font=("Roboto", 14), bg="#7312FF", fg="white", width="500",
                   height="2")
main_title.pack()

# Define Label Fields
from_label = Label(text="From", fg="white",bg="#213141")
from_label.place(x=22, y=70)
to_label = Label(text="To", fg="white",bg="#213141")
to_label.place(x=22, y=130)
subject_label = Label(text="Subject", fg="white",bg="#213141")
subject_label.place(x=22, y=190)
message_label = Label(text="Message", fg="white",bg="#213141")
message_label.place(x=22, y=250)


# Get and store data from users
_from = StringVar()
to = StringVar()
subject = StringVar()
message = StringVar()

def show_file_selector():
    global to
    Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
    to = askopenfilename()  # show an "Open" dialog box and return the path to the selected file

from_entry = Entry(textvariable=_from, width="40")
to_entry =  Entry(textvariable=to, width="40")
to_entry.place(x=22, y=155)

#to_entry = Button(mywindow, text="Choose file", width="20", height="1", command=show_file_selector, bg="#7312FF",fg="white")
#to_entry.place(x=22, y=155)

subject_entry = Entry(textvariable=subject, width="40")
message_entry = Entry(textvariable=message,width="40")

from_entry.place(x=22, y=100)
subject_entry.place(x=22, y=220)
message_entry.place(x=22, y=280,height=100)

# Submit Button
submit_btn = Button(mywindow, text="Send", width="15", height="2", command=send_data, bg="#7312FF",fg="white")
submit_btn.place(x=200, y=400)

mywindow.mainloop()